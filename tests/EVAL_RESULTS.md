# Seeded-error evaluation

- Documents: 26 (19 with planted issues, 7 clean)
- Planted issues caught: **19/19** (100%)
- Clean documents flagged (false positives): **0/7**
- Extra, unplanned findings on issue documents: 0

| Document | Expected | Found | Unplanned |
|---|---|---|---|
| promise_guaranteed | promise | promise | - |
| risk_free | promise | promise | - |
| superlative_best | superlative | superlative | - |
| fee_wrong | figure_mismatch | figure_mismatch | - |
| settle_wrong | figure_mismatch | figure_mismatch | - |
| stale_merchants | figure_stale | figure_stale | - |
| unsourced_pct | figure_unsourced | figure_unsourced | - |
| retired_name | terminology | terminology | - |
| signup_term | terminology | terminology | - |
| brand_case | terminology | terminology | - |
| tone_slang | tone_word | tone_word | - |
| exclaim | tone_exclaim | tone_exclaim | - |
| caps | tone_caps | tone_caps | - |
| long_sentence | readability | readability | - |
| disclaimer_missing | disclaimer | disclaimer | - |
| click_here | a11y_link | a11y_link | - |
| md_image | a11y_image | a11y_image | - |
| clean_1 | (clean) | - | - |
| clean_2 | (clean) | - | - |
| clean_3 | (clean) | - | - |
| clean_4 | (clean) | - | - |
| clean_5 | (clean) | - | - |
| clean_6 | (clean) | - | - |
| clean_7 | (clean) | - | - |
| comparison | comparison | comparison | - |
| implicit_promise | promise | promise | - |

Small hand-written test set for regression checking. It is not a measure of accuracy on real brand content.
