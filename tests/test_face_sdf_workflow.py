import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
import pmx4ue

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("face_sdf_profile", ROOT / "tools/face_sdf_profile.py")
profile_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile_module)


class FaceSDFWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.namespace = "/Game/PMX4UE/Example/v1"
        self.profile = dict(version=1, reviewed=True, review_evidence="Bind-pose/UV hemisphere inspected",
                            provider="pmx4ue", mesh=self.namespace+"/SK_Example",
                            destination=self.namespace+"/FaceSDF_v1", face_slot="顔", head_bone="頭",
                            reference_forward=[0, 2, 0], reference_left=[2, 1, 0])

    def validate(self):
        return profile_module.validate_profile(self.profile, self.namespace)

    def test_normalize_without_changing_input_or_requiring_english_bone_names(self):
        before = copy.deepcopy(self.profile)
        result = self.validate()
        self.assertEqual(result["reference_forward"], [0, 1, 0])
        self.assertEqual(result["reference_left"], [1, 0, 0])
        self.assertEqual(before, self.profile)

    def test_review_is_explicit(self):
        for key, value in (("reviewed", False), ("review_evidence", ""), ("head_bone", "None"),
                           ("face_slot", ""), ("provider", "guess")):
            original = self.profile[key]
            self.profile[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.validate()
            self.profile[key] = original

    def test_reject_invalid_axes(self):
        for axes in ([0, 0, 0], [float("nan"), 0, 0], [float("inf"), 0, 0],
                     [True, 0, 0], [0, 1], [0, 1, 0], [1.79e308, 1.79e308, 1.79e308]):
            self.profile["reference_left"] = axes
            with self.subTest(axes=axes), self.assertRaises(ValueError):
                self.validate()

    def test_namespace_and_object_paths(self):
        for path in ("/Game/Production", self.namespace+"Other/Face", self.namespace+"/../Face",
                     self.namespace+"/Face.Face", "/Game"):
            self.profile["destination"] = path
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.validate()

    def test_stage_requires_profile_and_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as folder:
            a = Path(folder)/"not-created"
            c = {"character": {"id": "Example"}, "pmx4ue": {
                "physics_profile": "physics.json", "engine": "UE", "blender": "Blender"}}
            with self.assertRaisesRegex(ValueError, "face_sdf_profile"):
                pmx4ue.recipe(c, Path(folder)/"Example.uproject", a, "face-sdf")
            c["pmx4ue"]["face_sdf_profile"] = "reviewed-face.json"
            result = pmx4ue.recipe(c, Path(folder)/"Example.uproject", a, "face-sdf")
            self.assertIn("face-sdf", pmx4ue.STAGES)
            self.assertIn("-AllowCommandletRendering", result["argv"])
            self.assertTrue(result["env"]["PMX4UE_SCRIPT"].endswith("ue_face_sdf_workflow.py"))
            self.assertEqual(result["env"]["PMX4UE_FACE_SDF_PROFILE"], "reviewed-face.json")
            self.assertFalse(a.exists())
