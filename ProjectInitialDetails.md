Problem Statement:
Corporate workers travelling overseas for a short business trips may face language barriers when communicating with local clients. Although English is commonly used for communicating with international countries, differences in language proficiency, grammar, pronunciation, and cultural expressions can still lead to misunderstandings.
Employees, whether working for local or international companies, may not have enough time or a practical need to learn the local language when travelling overseas for short business trips. This can be especially challenging for SMEs, which may have fewer resources to provide extensive language training. Existing translation tools mainly translate words and sentences without considering business context, tone, pronunciation, or the intended meaning.
BizLate aims to bridge this gap through an AI-assisted translation system that uses speech-to-text, language detection, and an LLM with a structured language database to analyse the user's message. It can identify unclear wording, inappropriate tone or formality, and potential translation errors before producing a clearer business-appropriate translation. The translated message can then be converted back into speech for more natural communication.

Methods for database detection:
-	We must store language information in a database using the appropriate data structure and LLM.
-	Models utilizing LLM or agentic methods, based on the correct data structure, are expected to serve as a bridging tool to facilitate communication in international business processes.

Target Users: Multinational Company

User Input: Speech to text, sentences to convey between the parties in the conversation

Use of AI: It will detect the language of both speaker and translate the message they want to convey. It will also be checking the tone/formality of the conversation and adjust the tone of the translation. The AI will then send the translated message to the program which will then convert it to speech for the user to listen.

Business rule: Based on the input tone/formalities, it should validate certain words/translation that does not fit the occasion to rule out miscommunication. It should also check whether it is outputting gibberish translation.

Git Repository Link:
https://github.com/Bloopswy/BizTranslate.git
