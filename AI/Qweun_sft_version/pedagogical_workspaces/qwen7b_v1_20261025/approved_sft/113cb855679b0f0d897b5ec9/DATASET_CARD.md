# BKQuiz: theory → novel quiz and pedagogical explanations

Only the latest human-approved candidate for each teacher job is exported.
Theory-to-quiz inputs contain theory and a blueprint, without a pre-existing question or answer.
Enrichment inputs contain the original question and all options, without the private answer key.
The public explanation covers the concept, application to the correct answer, and every option.
Exact citations, two blind option orders and a same-model critic are checked before human review.
These automated checks are not independent semantic proof. Human approval is not an expert-gold claim.

Main train contains at least 80% unique theory-to-quiz examples; excess enrichment is auxiliary only.
Do not concatenate the old 742-question release or the auxiliary pool into main train unchecked.
Contexts from the same 8-page block and near-duplicate components stay in a single split.
Original exam families keep their existing split. Duplicates prefer the held-out record.
The source PDFs were already seen in CPT: this is not a test on unseen textbooks.

The student remains Qwen3-1.7B and the verified 27-course CPT adapter. No training occurs here.
Reuse the pinned Qwen3 tokenizer with enable_thinking=False. Loss is on assistant content and EOS only.
Overlong records are excluded intact, never truncated. Inspect build_report.json before training.
Compare the pre-SFT and post-SFT student on the same held-out theory prompts with human scoring of
answer correctness, grounding, novelty, explanation and distractor quality. This gain is not yet measured.
