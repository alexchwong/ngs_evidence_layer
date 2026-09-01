from __future__ import annotations

import unittest
from pathlib import Path


class UIBatchQoLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = (Path(__file__).resolve().parents[1] / "ui" / "index.html").read_text(encoding="utf-8")

    def test_examples_batch_uses_compact_multiselect_dropdown(self):
        self.assertIn('id="batchCasePickerBtn"', self.page)
        self.assertIn('id="batchCaseMenu"', self.page)
        self.assertIn('aria-haspopup="true"', self.page)
        self.assertIn("setBatchCaseMenu", self.page)
        self.assertIn("document.addEventListener('click',()=>setBatchCaseMenu(false))", self.page)

    def test_batch_has_one_canonical_case_selector(self):
        self.assertNotIn('id="batchCaseSelect"', self.page)
        self.assertIn('id="casePaneSelect"', self.page)
        self.assertIn("sels=[$('casePaneSelect')]", self.page)

    def test_single_and_batch_share_phase_progress_component(self):
        self.assertIn('id="progressRows"', self.page)
        self.assertIn('function renderProgress()', self.page)
        self.assertIn('function progressSegments(', self.page)
        self.assertIn('class="progress-phase"', self.page)
        self.assertNotIn('id="stageRail"', self.page)

    def test_left_run_list_is_compact(self):
        self.assertIn('.run-id{font-size:10.5px', self.page)
        self.assertIn('.run-meta{font-size:9px', self.page)
        self.assertIn('.runs-list{flex:1 1 0;min-height:0;overflow-y:auto', self.page)

    def test_batch_child_navigation_uses_canonical_run_selection(self):
        self.assertIn("function chooseBatchChild(ref){if(!ref)return;if(state.selected!==ref){selectRun(ref);return}", self.page)
        self.assertIn("if(r?.kind==='batch-child')state.selectedBatchChild=id;else state.selectedBatchChild=''", self.page)
        self.assertIn("row.addEventListener('click',()=>chooseBatchChild(row.dataset.progressChild))", self.page)
        self.assertIn("$('casePaneSelect').addEventListener('change',e=>chooseBatchChild(e.target.value))", self.page)

    def test_console_state_is_cached_per_selected_run(self):
        self.assertIn("consoleCache:{}", self.page)
        self.assertIn("function saveConsoleTarget()", self.page)
        self.assertIn("function setConsoleTarget(ref)", self.page)
        self.assertIn("state.consoleCache[state.selected]", self.page)
        self.assertIn("setConsoleTarget(state.selected)", self.page)

    def test_batch_parent_does_not_implicitly_select_first_child(self):
        self.assertIn('Select case…', self.page)
        self.assertIn("if(r.kind==='batch')return state.selectedBatchChild||r.run_id", self.page)
        self.assertNotIn("kids[0]?.run_id", self.page)

    def test_lhs_controls_share_rhs_label_font_token(self):
        self.assertIn("--ui-label-size:11px", self.page)
        self.assertIn(".pane-title{font-family:var(--mono);font-weight:850;font-size:var(--ui-label-size)", self.page)
        self.assertIn(".lhs input,.lhs select,.lhs textarea,.lhs .source-switch button,.lhs .run-actions button{font-size:var(--ui-label-size)}", self.page)


if __name__ == "__main__":
    unittest.main()
