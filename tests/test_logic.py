import unittest

from meeting_translator.config import RuleSettings
from meeting_translator.exceptions import ValidationError
from meeting_translator.logic_layer import (ConfidenceCheckRule, LanguageMismatchRule, LogicManager, RejectRule,
                                            Rule, RuleEngine, ScoringStrategy, TensionRule, ToneIntensityScoring)
from meeting_translator.models import Outcome
from tests.helpers import good_ai, make_setup, utterance


class RuleTests(unittest.TestCase):
    def setUp(self):
        self.s = RuleSettings()
        self.u = utterance()

    def test_reject_rule(self):
        rule = RejectRule(self.s)
        self.assertEqual(rule.reasons(self.u, good_ai(translation="  ")), ["empty translation"])
        self.assertTrue(rule.fires(self.u, good_ai(detected_language="Other")))
        self.assertFalse(rule.fires(self.u, good_ai()))

    def test_confidence_rule_boundaries(self):
        rule = ConfidenceCheckRule(self.s)
        self.assertFalse(rule.fires(self.u, good_ai(language_confidence=0.6, translation_confidence=0.6)))
        self.assertEqual(len(rule.reasons(self.u, good_ai(language_confidence=0.59, translation_confidence=0.1))), 2)

    def test_language_mismatch_rule(self):
        rule = LanguageMismatchRule(self.s)
        self.assertFalse(rule.fires(self.u, good_ai(detected_language="English")))
        self.assertIn("Acme", rule.reasons(self.u, good_ai(detected_language="Chinese"))[0])

    def test_tension_rule_needs_all_three_fields(self):
        rule = TensionRule(self.s)
        angry = dict(tone="angry", intensity=4, tone_confidence=0.7)
        self.assertTrue(rule.fires(self.u, good_ai(**angry)))
        for weaken in ({"tone": "happy"}, {"intensity": 3}, {"tone_confidence": 0.69}):
            self.assertFalse(rule.fires(self.u, good_ai(**{**angry, **weaken})), weaken)

    def test_all_rules_are_substitutable_rules(self):
        for rule_class in (RejectRule, ConfidenceCheckRule, LanguageMismatchRule, TensionRule):
            rule = rule_class(self.s)
            self.assertIsInstance(rule, Rule)
            self.assertIsInstance(rule.reasons(self.u, good_ai()), list)
            self.assertIsInstance(rule.outcome, Outcome)

    def test_rule_is_abstract(self):
        with self.assertRaises(TypeError):
            Rule(self.s)


class ScoringTests(unittest.TestCase):
    def test_score_formula_and_cap(self):
        scoring = ToneIntensityScoring()
        self.assertEqual(scoring.score(good_ai(tone="neutral", intensity=1)), 10)
        self.assertEqual(scoring.score(good_ai(tone="angry", intensity=4)), 70)
        self.assertEqual(scoring.score(good_ai(tone="angry", intensity=5)), 80)

    def test_scoring_is_abstract(self):
        with self.assertRaises(TypeError):
            ScoringStrategy()


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.logic = LogicManager()
        self.u = utterance()

    def route(self, **ai):
        return self.logic.route(self.u, good_ai(**ai))

    def test_accept(self):
        decision = self.route()
        self.assertEqual((decision.outcome, decision.reasons), (Outcome.ACCEPT, ("clear and routine",)))

    def test_check_on_low_confidence_or_language_mismatch(self):
        self.assertEqual(self.route(translation_confidence=0.3).outcome, Outcome.CHECK)
        self.assertEqual(self.route(detected_language="Chinese").outcome, Outcome.CHECK)

    def test_tension_wins_over_check_but_keeps_doubts(self):
        decision = self.route(tone="angry", intensity=5, tone_confidence=0.9, translation_confidence=0.2)
        self.assertEqual(decision.outcome, Outcome.TENSION)
        self.assertEqual(len(decision.reasons), 2)

    def test_reject_beats_everything_and_scores_zero(self):
        decision = self.route(detected_language="Other", tone="angry", intensity=5)
        self.assertEqual((decision.outcome, decision.score), (Outcome.REJECT, 0))

    def test_ai_output_changes_the_outcome(self):
        self.assertNotEqual(self.route(tone="neutral").outcome, self.route(tone="angry", intensity=5).outcome)

    def test_custom_thresholds_change_routing(self):
        strict = LogicManager(RuleSettings(tension_min_intensity=2))
        self.assertEqual(strict.route(self.u, good_ai(tone="angry", intensity=2)).outcome, Outcome.TENSION)
        self.assertEqual(self.logic.route(self.u, good_ai(tone="angry", intensity=2)).outcome, Outcome.ACCEPT)

    def test_open_closed_new_rule_and_scoring_without_editing_manager(self):
        class AlwaysCheck(Rule):
            outcome = Outcome.CHECK

            def reasons(self, utterance, analysis):
                return ["custom rule"]

        class Flat(ScoringStrategy):
            def score(self, analysis):
                return 7

        logic = LogicManager(engine=RuleEngine([AlwaysCheck(RuleSettings())]), scoring=Flat())
        decision = logic.route(self.u, good_ai())
        self.assertEqual((decision.outcome, decision.score, decision.reasons), (Outcome.CHECK, 7, ("custom rule",)))


class RuleSettingsTests(unittest.TestCase):
    def test_from_dict_overrides_and_validates(self):
        s = RuleSettings.from_dict({"tension_min_intensity": 3, "tension_tones": ["angry"]})
        self.assertEqual(s.tension_min_intensity, 3)
        self.assertEqual(len(s.tension_tones), 1)
        for bad in ({"tension_min_intensity": 9}, {"tension_tones": ["bored"]}, {"min_language_confidence": 2},
                    {"context_sentences": -1}, {"tension_min_intensity": True}, "text"):
            with self.assertRaises(ValidationError, msg=repr(bad)):
                RuleSettings.from_dict(bad)

    def test_load_missing_or_corrupt_file_gives_defaults(self):
        from tests.helpers import TempDir
        with TempDir() as folder:
            self.assertEqual(RuleSettings.load(TempDir.join(folder, "none.json")), RuleSettings())
            path = TempDir.join(folder, "rules.json")
            with open(path, "w") as handle:
                handle.write("{broken")
            self.assertEqual(RuleSettings.load(path), RuleSettings())
            with open(path, "w") as handle:
                handle.write('{"tension_min_intensity": 2}')
            self.assertEqual(RuleSettings.load(path).tension_min_intensity, 2)


if __name__ == "__main__":
    unittest.main()
