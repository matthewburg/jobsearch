# Resume Builder

Turns your resume content into a styled, parsable PDF (and soon DOCX). Content and design are separate:

- **Content:** `profile/resume.json`, in the [JSON Resume](https://jsonresume.org/schema) format: basics, work, projects, skills, certificates, education. Claude drafts it from your experience bank (`profile/roles/`, `bullet-bank.md`), and every tailored resume is a copy of it with different choices.
- **Design:** a style is one stylesheet in [themes/](themes/). Every style shares the same single-column structure, so swapping styles never changes what a parser reads.

```bash
python -I resume-builder/build.py
```

```bash
python -I resume-builder/build.py --style modern
```

The first builds every style into `resumes/styles/` (HTML, PDF, and a side-by-side `index.html` gallery). The second builds one. Tailored versions use `--data resumes/<company>/resume.json --out resumes/<company>`.

PDFs are printed by headless Chrome or Edge (Edge ships with Windows), using a throwaway browser profile. Nothing to install.

## The styles

| Style | Look | Good for |
|---|---|---|
| **Modern** | Calibri, left-aligned, one teal accent, small uppercase section labels | Most tech and product roles. The safe default. |
| **Executive** | Cambria headings over a Calibri body, navy top rule, contact block on the right | Director and above, larger and more traditional companies |
| **Classic** | Georgia, centered small-caps name, thin rules | Conservative fields, government, education |
| **Builder** | Calibri plus Consolas details (dates, contact, tools), warm accent, square section markers | Hands-on, technical, AI and dev-tools roles |

Fonts are ones Word has everywhere (Calibri, Cambria, Georgia, Consolas), so a DOCX version looks the same as the PDF.

## Parsability rules (all styles follow these)

Applicant tracking systems (Workday, Greenhouse, Lever, iCIMS, …) pull the text out of your file and guess at its structure. What keeps that working:

1. **One column, in reading order.** No sidebars, no text boxes, no tables for layout. Two-column designs often come out with lines interleaved.
2. **Real text only.** No text in images, icons, or charts. No skill bars or ratings.
3. **Standard section names:** Summary, Experience, Projects, Skills, Education, Certifications.
4. **Contact details in the body**, not in a page header or footer. Some parsers skip those.
5. **Company, title, and dates on predictable lines**, with dates as "Mon YYYY – Mon YYYY".
6. **No letter-spaced headings.** Caught in testing: "EXPERIENCE" with wide letter spacing came out of the PDF as "E X P E R I E N C E".
7. **No transparency or effects on text.** Also caught in testing: faded text was pulled out of reading order, to the end of the page.
8. **Common fonts, 10–11 pt body,** and 1–2 pages (2 is normal past ~10 years).

**Check a PDF the way a parser sees it:** open it, select all, copy, and paste into a plain text editor. It should read top to bottom in the right order. (Claude does this check by extracting the text after each build.)

## Picking a style: the alignment step

Before any tailoring, the person and Claude agree on the base resume once:
1. **Build the gallery** with their real content and look at all four styles side by side.
2. **Pick a style.** Tweak colors, fonts, or spacing in its stylesheet if wanted (changes stay parse-safe as long as the rules above hold).
3. **Settle the content decisions:** headline, summary, title framing, which projects, section order, one or two pages.
4. **That becomes the base.** Every tailored resume starts from it and only changes which bullets lead, the summary, the skills order, and which projects appear. The design stays put.

## Reviewing, and teaching it as you go

Review happens over a few sessions, in plain language: "Rocket isn't its own product", "cut the soft skills", "the summary sounds stiff."
- **Claude makes each correction and says whether it agrees, and why.** If a change would hurt the resume, it says so.
- **Every correction goes into `profile/resume-notes.md`** as a decision, the reasoning, and how to apply it.
- **Claude reads that file before drafting or tailoring anything,** so the same understanding carries into every future resume and cover letter.

## What to expect from generated resumes

- **Every claim comes from the experience bank.** Claude rewords, reorders, and trims; it doesn't invent metrics or experience. Anything unsure gets flagged for you.
- **Tailoring is selection.** A tailored resume shows different strengths for the role. It's not a different person.
- **You review every resume before it goes anywhere.** Nothing is ever submitted automatically.

## Coming next
- **DOCX output** from the same content and style (fonts, colors, and spacing carried over), for applications that ask for Word.
- **Tailoring command:** a job from the report plus the base resume produces `resumes/<company>/`, with a short note on what changed and why.
