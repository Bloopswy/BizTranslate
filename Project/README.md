# Meeting Translator

A live interpreter for a **business meeting between two parties** who speak **English, Indonesian or Chinese**.
Each sentence is spoken (or typed), transcribed to text, and **Google's Gemma model reads the text only (never
the audio), translates it into the other party's language and reads its tone**. The screen always shows the
**latest translation plus the 3 sentences before it, each with a timestamp**.

## Problem statement and target users
Corporate workers travelling overseas for a short business trips may face language barriers when communicating with local clients. Although English is commonly used for communicating with international countries, differences in language proficiency, grammar, pronunciation, and cultural expressions can still lead to misunderstandings. Employees, whether working for local or international companies, may not have enough time or a practical need to learn the local language when travelling overseas for short business trips. This can be especially challenging for SMEs, which may have fewer resources to provide extensive language training. Existing translation tools mainly translate words and sentences without considering business context, tone, pronunciation, or the intended meaning. BizLate aims to bridge this gap through an AI-assisted translation system that uses speech-to-text, language detection, and an LLM with a structured language database to analyse the user's message. It can identify unclear wording, inappropriate tone or formality, and potential translation errors before producing a clearer business-appropriate translation. The translated message can then be converted back into speech for more natural communication.
