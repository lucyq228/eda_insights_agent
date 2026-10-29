# One proposal format, different investigations

Present an objective, this three-column table, boundaries/gaps, and a recommendation the user
can accept or revise. These are illustrative sequences, not claims about the datasets and not
mandatory stages. Use actual columns and feasible parameters after profiling.

| Use case / sequential question | Purpose | Tools |
| --- | --- | --- |
| Retail: how do customers, visits, quantity and unit value reconcile sales? | Establish meaningful accounting components | business-summary |
| Where are sales concentrated and which components explain group differences? | Separate group size from purchasing behavior | business-summary; declared aggregate views |
| Which priority patterns warrant deeper investigation? | Follow observed gaps within agreed groups | Conditional pair-deep-dive / segment-breakdown |
| Are differences consistent across stores and periods? | Assess composition and exposure | temporal-diagnostics; panel tools only if suitable |
| Housing: how do prices vary across the agreed market? | Establish the population and price distribution | automatic target overview; segment-breakdown |
| Which property factors carry the strongest signals? | Prioritize individual and joint associations | target-associations; driver-importance |
| Do those signals hold among similar homes, and where do curves appear? | Deepen under agreed location/size comparisons | Conditional partial-correlation / nonlinearity-check |
| Attrition: what proportion left, and where are counts and rates concentrated? | Define the positive class, denominator and observation window | automatic target overview; segment-breakdown |
| Which pre-departure factors carry the strongest signals? | Prioritize observed associations without outcome leakage | target-associations; driver-importance |
| Do those relationships survive relevant controls and vary by group? | Assess consistency and actionable patterns | Conditional partial-correlation / segment-correlation |

Housing prices must not be summed as sales. Attrition has no temporal pathway without dates;
exit interviews are not pre-departure predictors. Retail unit value includes product mix.
All use cases end with evidence synthesis, limitations, and actions requiring validation.

## Adaptive question in the existing scope schema

```json
{
  "id": "H3",
  "statement": "Do the priority relationships persist within the agreed comparison groups?",
  "rationale": "Check whether the strongest overall signals reflect differences in group composition.",
  "support_criteria": "Compare direction, magnitude, uncertainty and coverage; an inconclusive result is valid.",
  "pathway": [],
  "followup_when": "Earlier screening finds a material relationship and scoped groups have adequate coverage; otherwise explain why this stage is not pursued.",
  "candidate_tools": ["segment-correlation", "partial-correlation"]
}
```

Use this only in exploratory mode. Initial questions still have concrete executable pathways.
The analyst selects parameters after reading evidence and records the question ID and reason.
The reviewer requires evidence for either the answer or the decision not to pursue a conditional
question. A missing data area belongs in boundaries/gaps, not in the executable manifest.
