from __future__ import annotations

from ncdev.models import ConsensusDoc, HumanQuestion, HumanQuestionsDoc, ModelAssessment


def _line_set(text: str) -> set[str]:
    return {line.strip() for line in text.splitlines() if line.strip()}


def build_human_questions(assessments: list[ModelAssessment], consensus: ConsensusDoc) -> HumanQuestionsDoc:
    if not consensus.requires_human:
        return HumanQuestionsDoc(questions=[])

    prompts: list[HumanQuestion] = []
    by_model = {a.model: a for a in assessments}
    model_names = sorted(by_model.keys())

    if len(model_names) >= 2:
        left, right = by_model[model_names[0]], by_model[model_names[1]]
        only_left = sorted(_line_set(left.output) - _line_set(right.output))[:5]
        only_right = sorted(_line_set(right.output) - _line_set(left.output))[:5]
        prompts.append(
            HumanQuestion(
                id="hq-001",
                question="Model outputs diverge. Which direction should be preferred for the next phase?",
                context=(
                    f"{left.model} unique lines: {only_left if only_left else ['none']}; "
                    f"{right.model} unique lines: {only_right if only_right else ['none']}"
                ),
                options=[left.model, right.model, "hybrid-manual-review"],
            )
        )

    if consensus.conflicts:
        prompts.append(
            HumanQuestion(
                id="hq-002",
                question="Consensus gate failed. Should execution stop or continue in advisory mode?",
                context="; ".join(consensus.conflicts),
                options=["stop", "continue-advisory"],
            )
        )

    return HumanQuestionsDoc(questions=prompts)
