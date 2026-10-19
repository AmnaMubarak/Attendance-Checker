# What I unlearned

> **Note to reviewer:** this draft reflects what the AI could observe
> happening in this build; the voice is first-person but the choices
> and tone are open to Amna's edit before submission.

## 1. "If AI can write it in one shot, I should let it"

The habit I had to drop. Before this, when the model offered to
"just build it", I would say yes and clean up later. On Day 1 I
instead told the model to **propose, not build**, and to wait for my
review. That one sentence changed the shape of the whole project.

What it bought me:

* A frozen anomaly list on paper before any detector existed.
* Pinned decisions on five open ambiguities (`max_gap_days`, half-day
  leave, weekly caps, leave on unscheduled days, unusual-date
  warnings) before a single line of detection code was committable.
* A design document (`Final directive.md`) that the implementation
  could be checked against, not a design that was reverse-engineered
  from code.

What it cost me:

* Two review rounds on Day 1 instead of one. Honestly, worth it.

## 2. "Trust the first output; iterate later"

I unlearned this and replaced it with **two review passes before
anything was written**. Round 2 of the design review surfaced eight
specific changes I would have missed if I had jumped to code
(renaming `MISSING_ATTENDANCE` to `UNRECORDED_ATTENDANCE` to drop
the implication of absence, forcing `max_gap_days` to use strict
greater-than, pinning half-day leave as a documented limitation
rather than silently flagging it as a bug, and so on).

The lesson is that the first draft of an AI design is a strong
*starting* position, not a shippable one. The second pass is where
my values about *this specific user* show up.

## 3. "Just run it and see what happens"

I replaced this with **tests before features**. Day 1 shipped the
schema validator with 36 tests and zero detectors. The detectors
could then be written against a known-good surface, and when the
Day 2 detectors failed on their first run it was because of a comma
inside a fixture's `notes` column (my mistake), not because the
schema was wrong. The failure was diagnosable in seconds instead of
hours.

## 4. "Features are the deliverable"

Not here. The deliverable included:

* A spec that forbids five accusatory words in any output, verified
  by a parametrized test over every detector.
* A `source_row_index` on every flag that points back to the exact
  row of the original CSV, so a reviewer can audit what the tool
  did.
* A `.copy(deep=True)` on the input and an assertion in tests that
  the pipeline does not mutate the DataFrame passed to it.

These are not features. They are the shape of the trust the tool is
asking for. Unlearning the "features are the deliverable" habit
meant giving them equal weight to anomaly detection.

## 5. "Logs are for successes"

The `daily_log.md` records three mistakes I would normally have
cleaned up quietly:

* Day 2: the first `pytest` run was red because fixture `notes`
  contained commas that pandas tokenized as extra fields. Twelve
  tests failed. I rewrote the four fixtures.
* Day 2.5: the sample-data generator accidentally injected a second
  `CONTRADICTORY_LEAVE` because the row it picked for duplication
  happened to be a leave day.
* Day 3: `pd.to_csv` serialized dates as `DD/MM/YYYY` using the
  Windows locale, breaking the schema smoke test on the generated
  sample. One extra `.dt.strftime("%Y-%m-%d")` call fixed it.
* Day 5: `ModuleNotFoundError` when launching Streamlit because
  Streamlit does not read `conftest.py`.

Writing them down was more useful than hiding them. The log is now
a document of what the project actually was, not what I wish it had
been.

## What I did not change

I was already careful about keeping employee data fictional, about
not shipping sensitive thresholds as "truth", and about writing
documentation that a non-engineer can read. Those were already
habits, not unlearning.

***

*One sentence summary:* I unlearned the habit of treating AI as a
code-production machine and relearned it as a design partner that
needs to be stopped, questioned, and told what the deliverable
*actually is* before any code gets written.
