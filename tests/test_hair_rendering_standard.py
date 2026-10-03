"""Documentation routing regressions, not proof of UE rendering or agent behavior."""
from pathlib import Path
import json
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class HairStandardTests(unittest.TestCase):
    def read(self, name):
        return (ROOT / name).read_text(encoding='utf-8-sig')

    def test_agent_entry_points_route_to_standard(self):
        for name in ('AGENTS.md', 'README.md', 'skills/pmx-to-ue/references/materials.md',
                     'docs/hair-bangs-workflow.md', 'docs/material-families.md',
                     'docs/material-quality-contract.md', 'docs/agent-material-workflow.md',
                     'docs/reference-implementation-transfer.md'):
            self.assertIn('hair-rendering-standard.md', self.read(name), name)

    def test_templates_require_real_assembly_not_old_hair_exclusion(self):
        for name in ('templates/material-design.md', 'templates/material-review.md'):
            self.assertIn('hair-assembly.md', self.read(name), name)
        record = self.read('templates/hair-assembly.md')
        for item in ('FringeDepth', 'BrowPeek', 'FringeShadow', 'EyePeek',
                     'SourceClip', 'R/G', '重载', 't.MaxFPS=200'):
            self.assertIn(item, record)
        self.assertNotIn('原不透明层排除、半透层接入', self.read('templates/material-design.md'))

    def test_standard_distinguishes_math_integration_and_game_acceptance(self):
        text = self.read('docs/hair-rendering-standard.md')
        for item in ('不要求挖掉', '先插值再阈值', '完整原着色', 'CoverageMode',
                     '没有完整刘海装配的一键阶段', '静止也测', '未实现参考的侧向弧度'):
            self.assertIn(item, text)

    def test_new_docs_are_portable_without_reference_project_paths(self):
        for name in ('docs/hair-rendering-standard.md', 'templates/hair-assembly.md'):
            text = self.read(name)
            self.assertNotRegex(text, r'[A-Za-z]:[\\/]')
            self.assertNotIn('Nikketa', text)
            self.assertNotIn('Stencil-140', text)

    def test_local_markdown_links_resolve(self):
        for name in ('docs/hair-rendering-standard.md', 'docs/hair-bangs-workflow.md',
                     'docs/reference-implementation-transfer.md'):
            path = ROOT / name
            for target in re.findall(r'\]\(([^)]+\.md)\)', self.read(name)):
                self.assertTrue((path.parent / target).is_file(), (name, target))

    def test_new_hair_template_prefers_band_without_approving_fit(self):
        config = json.loads(self.read('templates/head_hair.example.json'))
        self.assertEqual(config['highlight_mode'], 'head_band')
        self.assertIs(config['reviewed'], False)
        self.assertIs(config['band']['reviewed'], False)


if __name__ == '__main__':
    unittest.main()
