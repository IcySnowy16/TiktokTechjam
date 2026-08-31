"""Paraphrase stress tests for the dialog state machine.

Cue wordings here are deliberately NOT copied from the evaluator's templates —
they simulate the paraphrasing the private session set may introduce.
"""

from __future__ import annotations

import unittest

from starter.dialog_state import DialogStateMachine, SessionState


def make_state() -> SessionState:
    return SessionState(session_id="test", user_profile={})


class BoundaryDetectionTest(unittest.TestCase):
    PARAPHRASES = [
        "I don't have a preference for color; please use your judgment.",
        "Honestly the color doesn't matter to me, you decide.",
        "No preference there - whatever you think works.",
        "I'm not particular about that, up to you.",
        "Either is fine with me, you pick.",
        "I really don't mind, use your discretion.",
        "I'm not fussy about the color at all.",
        "Open to anything on that front.",
    ]

    def test_paraphrased_boundary_cues_retire_the_asked_attribute(self):
        machine = DialogStateMachine()
        for phrase in self.PARAPHRASES:
            state = make_state()
            state.last_ask_attribute = "color"
            parsed = machine.update(state, phrase, turn=3)
            self.assertIn("color", state.boundary_attributes, msg=phrase)
            self.assertEqual(parsed.boundary_attr, "color", msg=phrase)
            self.assertEqual(parsed.filled, [], msg=phrase)


class OverrideDetectionTest(unittest.TestCase):
    PARAPHRASES = [
        "Actually, ignore my earlier preference. What I need is: black leather boots.",
        "Scratch that - what matters now is: black leather boots.",
        "On second thought, forget what I said before: black leather boots.",
        "Please disregard the earlier requirement. I want: black leather boots.",
        "I've changed my mind, the priority is: black leather boots.",
        "Never mind the last thing, what I really need is: black leather boots.",
    ]

    def test_paraphrased_override_cues_trigger_targeted_erasure(self):
        machine = DialogStateMachine()
        for phrase in self.PARAPHRASES:
            state = make_state()
            machine.update(state, "I'm looking for boots. A key requirement is: suede material.", turn=1)
            parsed = machine.update(state, phrase, turn=3)
            self.assertTrue(parsed.override, msg=phrase)
            filled_attrs = [attribute for attribute, _ in parsed.filled]
            self.assertEqual(len(filled_attrs), 1, msg=phrase)
            new_attr = filled_attrs[0]
            values = state.slots[new_attr]
            self.assertEqual(len(values), 1, msg=phrase)
            self.assertIn("black leather boots", values[0].text, msg=phrase)

    def test_override_leaves_other_slots_intact_but_decayed(self):
        machine = DialogStateMachine()
        state = make_state()
        state.last_ask_attribute = "budget"
        machine.update(state, "For that, what matters is: budget around $25.", turn=2)
        state.last_ask_attribute = None
        machine.update(state, "Scratch that, what I need is: red cotton dress.", turn=3)
        self.assertIn("budget", state.slots)
        self.assertLess(state.slots["budget"][0].weight, 1.2)


class RegularReplyTest(unittest.TestCase):
    def test_constraints_are_filed_under_asked_attribute(self):
        machine = DialogStateMachine()
        state = make_state()
        state.last_ask_attribute = "material"
        machine.update(state, "For that, what matters is: 100% ring-spun cotton.", turn=2)
        self.assertTrue(any("cotton" in v.text for v in state.slots.get("material", [])))

    def test_classifier_corrects_misfiled_attribute(self):
        machine = DialogStateMachine()
        state = make_state()
        state.last_ask_attribute = "feature"
        machine.update(state, "For that, what matters is: color: navy blue.", turn=2)
        self.assertIn("color", state.slots)

    def test_exhausted_reply_marks_attribute_not_boundary(self):
        machine = DialogStateMachine()
        state = make_state()
        state.last_ask_attribute = "style"
        machine.update(state, "I don't have an additional preference for style.", turn=4)
        self.assertIn("style", state.exhausted_attributes)
        self.assertNotIn("style", state.boundary_attributes)


class InitialMessageTest(unittest.TestCase):
    def test_buying_initial_extracts_category_and_constraint(self):
        machine = DialogStateMachine()
        state = make_state()
        machine.update(
            state, "I'm looking for Jewelry Earrings. A key requirement is: sterling silver.", turn=1
        )
        self.assertIn("jewelry", state.category_terms)
        self.assertTrue(state.slots)

    def test_browsing_initial_extracts_category_only(self):
        machine = DialogStateMachine()
        state = make_state()
        machine.update(state, "I'm looking for Shoes Sandals, but I'm still exploring.", turn=1)
        self.assertIn("sandals", state.category_terms)
        self.assertEqual(state.slots, {})


if __name__ == "__main__":
    unittest.main()
