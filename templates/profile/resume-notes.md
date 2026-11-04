# Resume Decisions

The corrections and choices you make while reviewing resumes, **with the reasoning**, so every future resume, cover letter, and profile blurb applies the same understanding without you repeating it. Claude reads this before drafting or tailoring anything and adds an entry whenever you correct something.

Each entry has: **the decision**, **why** (your reason, plus Claude's view if it agrees, disagrees, or adds something), and **how to apply** it. Title framing and the "never mention" list live in `targets.md`.

As entries pile up, keep a short **"Current rules"** list at the top that sums up everything below (later entries win). When a correction is a reusable phrase (a retired number, a tool you don't use, a claim worded too strongly), Claude also adds it to `resume-rules.json`, so `resume-builder/check.py` flags it in every draft, old or new.

---

## Example: how to name your old team (date)

**Decision:** call it "the payments platform team," not "Project Atlas."

**Why:** Atlas was an internal codename that nobody outside the company would recognize.

**How to apply:** use the plain description everywhere. Mention the codename only if a role at that same company asks for it.
