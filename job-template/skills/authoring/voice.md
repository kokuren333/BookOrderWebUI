# Voice: write like an author who has done the research

Read this before drafting, expanding, rewriting or editing prose in a Claude-orchestrated job. The user's
instructions (printed with every task) still govern voice; this skill replaces the timid default register that AI
drafts fall into when nobody asks for anything else.

## The problem this skill exists for

A research-strong but defensive draft reads like this:

> 生成AIの活用には様々な可能性がある一方で、注意すべき点も多く、一概には言えません。状況に応じて慎重に検討することが重要です。

Every clause is defensible and the paragraph says nothing. The reader paid for a book, not for a disclaimer. The
evidence map (research/evidence/<chapter>.yaml) exists so that you know exactly how strong each claim is — use that
knowledge to commit.

## Rules

1. **Calibrate, don't hedge by reflex.** `strength: strong` → state it plainly and cite it. `moderate` → state it with
   its scope ("2019〜2023年の国内調査では…"). `contested` → name the disagreement once, say which way the evidence leans
   and why. `weak` → either attribute it ("Xは…と主張する") or leave it out. Never put 「〜と考えられる」「可能性がある」
   on a strong claim; never present a weak one as fact.
2. **One precise caveat beats five vague ones.** Replace 「注意が必要です」 with what exactly fails, when, and how often.
   If you cannot say that, delete the caveat.
3. **Take positions the evidence supports.** A chapter has a point. Open with it or build to it, and let the reader see
   you arguing it. Balance means representing real disagreement accurately, not splitting every difference.
4. **Concrete before abstract.** Lead with the case, number, mechanism or scene from `sharp_findings`, then generalise.
   Prefer "who did what, when, with what result" to "さまざまな取り組みが行われている".
5. **Cut boilerplate.** No 「〜が重要です」 as a conclusion, no 「今後の動向が注目されます」 as an ending, no 「専門家に相談
   しましょう」 unless the book is a practical guide and the situation genuinely requires it (then say which specialist
   and why). No ritual 「本章では〜を見てきた」 recaps unless the editorial plan has a summary.
6. **Vary the rhythm.** Mix short declarative sentences with longer explanatory ones. Avoid chains of 「〜であり、〜であるが、
   〜であるため」. End paragraphs on the substantive point, not on a softener.
7. **Trust the reader.** Explain once, at the right depth for the audience in the Book Bible. Do not pre-empt every
   objection; answer the ones a smart reader would actually raise.
8. **Cite evidence, not background.** Specific numbers, findings, recent developments, contested points and
   recommendations carry an evidence citation. General knowledge these readers already accept needs none — do not
   decorate it with background sources (they never appear in the back matter).
9. **Integrity is non-negotiable.** Bold prose never outruns the sources: every factual sentence is still backed by an
   evidence-role citation. Confidence comes from the evidence map, not from tone.

## Self-check before `bookorder done`

- Run `bookorder voice --chapter <id>`. It lists hedge/boilerplate density, the densest paragraphs, and hedged
  sentences whose citations the evidence map rates strong. Fix those; a low number is not a goal in itself.
- Read the chapter's first and last paragraph aloud in your head: does each make a claim a reader could disagree with?
- For each section ask "what would the reader lose if this section were deleted?" If nothing, rewrite or cut it.
- Optionally `bookorder delegate factcheck <id>`: Codex checks every factual sentence against the source text and
  flags `overhedged` sentences as well as unsupported ones.

Where the user asked for a cautious, neutral or hedged register, follow the user; record it in plan/user-intent.yaml.
