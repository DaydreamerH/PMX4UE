import copy
import json
import math
from pathlib import Path
import tempfile
import unittest
import importlib.util
import sys
import types
from unittest.mock import MagicMock, patch

from tools.retarget_pose_math import axis_angle, forward, rotate
from tools.retarget_workflow import (compile_pair, draft_model, draft_pair, fingerprint,
                                    reference_identity, validate_model, asset_path)
from tools.pose_workflow import main, write_bundle


def fixture():
    """Two distinct skeletons: different names, proportions and component axes."""
    sides, models = {}, {}
    for side, prefix, scale, turn in (("source", "a", 1.2, 70), ("target", "b", 1., -20)):
        q = axis_angle((0, 0, 1), turn)
        bones = []
        rows = [("root", -1, (0,0,0)), ("pelvis", 0, (0,0,85)),
                ("spine", 1, (0,0,8)), ("chest", 2, (0,0,25)),
                ("armL", 3, (15,0,0)), ("elbowL", 4, (25,0,-10)), ("wristL", 5, (20,0,-5)),
                ("armR", 3, (-15,0,0)), ("elbowR", 7, (-25,0,-10)), ("wristR", 8, (-20,0,-5)),
                ("hipL", 1, (10,0,-5)), ("kneeL", 10, (-1,1,-37)), ("ankleL", 11, (-1,-1,-37)),
                ("hipR", 1, (-10,0,-5)), ("kneeR", 13, (1,1,-37)), ("ankleR", 14, (1,-1,-37))]
        for i,(name,parent,pos) in enumerate(rows):
            pos = tuple(x*scale for x in pos)
            bones.append(dict(name=prefix+name, parent=parent, ref_position=pos, local_position=pos,
                ref_rotation=q if i==0 else (0,0,0,1), offset=(0,0,0,1),
                ref_scale=(1,1,1), local_scale=(1,1,1), global_scale=(1,1,1)))
        forward(bones)
        chain = lambda *ns: [prefix+n for n in ns]
        chains = {prefix+"Spine": chain("spine", "chest"), prefix+"LA": chain("armL","wristL"),
                  prefix+"RA": chain("armR","wristR"), prefix+"LL": chain("hipL","ankleL"), prefix+"RL": chain("hipR","ankleR")}
        sides[side] = dict(rig="/Game/"+prefix+"Rig", pelvis=prefix+"pelvis", chains=chains,
            snapshot=dict(status="inspected", mesh="/Game/"+prefix+"Mesh", pose="Default Pose", side=side,
                          root_offset=[0,0,0], bones=bones))
        models[side] = dict(basis={k: rotate(q,v) for k,v in dict(left=(1,0,0), forward=(0,1,0), up=(0,0,1)).items()},
            roles=dict(pelvis=prefix+"pelvis", spine=chain("spine","chest"),
                arms=dict(left=chain("armL","elbowL","wristL"), right=chain("armR","elbowR","wristR")),
                legs=dict(left=chain("hipL","kneeL","ankleL"), right=chain("hipR","kneeR","ankleR"))),
            spine_chain=prefix+"Spine", limb_chains=dict(arms=dict(left=prefix+"LA", right=prefix+"RA"),
                                                       legs=dict(left=prefix+"LL", right=prefix+"RL")))
    inv = dict(schema="pmx4ue.pose-inventory.v1", retargeter="/Game/Base", sides=sides,
               mappings={"b"+n: "a"+n for n in ("Spine","LA","RA","LL","RL")}, ops=[])
    review = dict(by="test agent", rationale="synthetic known hierarchy", evidence=["synthetic fixture, not real asset acceptance"], unresolved=[])
    for side in models:
        models[side] = {**draft_model(inv,side,side), **models[side], "review":copy.deepcopy(review),
                       "role_evidence":{k:["fixture construction"] for k in ("pelvis","spine","arms","legs","basis")}}
    pair = draft_pair(inv)
    pair.update(namespace="/Game/Experiment", output_retargeter="/Game/Experiment/Pose_v1", review=review)
    for side in models:
        pair["sides"][side]["posture_checks"] = [dict(start=models[side]["roles"]["pelvis"],
            end=models[side]["roles"]["spine"][1], up_axis=[0,0,1], max_tilt_degrees=5)]
    return inv, models, pair


class WorkflowTests(unittest.TestCase):
    def ue_module(self, name, unreal):
        path = Path(__file__).resolve().parents[1]/"tools"/(name+".py")
        spec = importlib.util.spec_from_file_location("tested_"+name,path)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{"unreal":unreal}): spec.loader.exec_module(module)
        return module

    def test_native_builder_rejects_tampering_before_duplicate(self):
        inv,models,pair = fixture()
        profile = compile_pair(inv,models,pair)["profile"]
        ue = MagicMock()
        class Asset: pass
        ue.IKRetargeter = Asset
        ue.load_asset.return_value = Asset()
        ue.EditorAssetLibrary.does_asset_exist.return_value = False
        module = self.ue_module("ue_retarget_pose",ue)
        profile["sides"]["source"]["left_axis"] = [1,0,0]
        collector = types.SimpleNamespace(collect=lambda a: inv)
        with tempfile.TemporaryDirectory() as folder, patch.dict(sys.modules,{"ue_pose_inventory":collector}):
            with self.assertRaisesRegex(ValueError,"differs from reviewed"):
                module.build(profile,pair["namespace"],Path(folder)/"report.json")
        ue.EditorAssetLibrary.duplicate_asset.assert_not_called()

    def test_native_builder_rejects_stale_input_before_duplicate(self):
        inv,models,pair = fixture()
        profile = compile_pair(inv,models,pair)["profile"]
        ue = MagicMock()
        class Asset: pass
        ue.IKRetargeter = Asset
        ue.load_asset.return_value = Asset()
        ue.EditorAssetLibrary.does_asset_exist.return_value = False
        module = self.ue_module("ue_retarget_pose",ue)
        inv["ops"].append(dict(type="Changed",enabled=True))
        with tempfile.TemporaryDirectory() as folder, patch.dict(sys.modules,{"ue_pose_inventory":types.SimpleNamespace(collect=lambda a: inv)}):
            with self.assertRaisesRegex(ValueError,"Stale pair"):
                module.build(profile,pair["namespace"],Path(folder)/"report.json")
        ue.EditorAssetLibrary.duplicate_asset.assert_not_called()

    def test_reload_rejects_same_process_and_leaves_visual_pending(self):
        import os
        inv,_,_ = fixture()
        snapshots = {s: d["snapshot"] for s,d in inv["sides"].items()}
        report = dict(status="saved_native_readback_passed_needs_visual_review",process_id=os.getpid(),
                      before=snapshots,after=snapshots,profile=dict(retargeter="/Game/Base",output_retargeter="/Game/New"))
        ue = MagicMock()
        class Asset: pass
        ue.IKRetargeter = Asset
        ue.load_asset.return_value = Asset()
        module = self.ue_module("ue_pose_reload",ue)
        with tempfile.TemporaryDirectory() as folder, patch.dict(sys.modules,{"unreal":ue,
                "ue_retarget_pose":types.SimpleNamespace(inspect=lambda asset,side: snapshots[side])}):
            root = Path(folder)
            write_bundle(root/"same",{"build.json":report})
            with self.assertRaisesRegex(ValueError,"separate"):
                module.check(root/"same/build.json",root/"same/reload.json")
            report["process_id"] = -1 # Deliberately different synthetic process.
            write_bundle(root/"fresh",{"build.json":report})
            result = module.check(root/"fresh/build.json",root/"fresh/reload.json")
            self.assertEqual(result["visual_review"],"pending")
            self.assertEqual(result["animation_review"],"pending")
            ue.EditorAssetLibrary.save_loaded_asset.assert_not_called()

    def test_cross_axes_proportions_and_no_input_mutation(self):
        inv,models,pair = fixture()
        old = copy.deepcopy((inv,models,pair))
        result = compile_pair(inv,models,pair)
        self.assertEqual((inv,models,pair), old)
        for side in models:
            p = result["predictions"][side]
            self.assertLess(max(s["final_degrees"] for s in p["segments"]), .001)
            for a,b in zip(inv["sides"][side]["snapshot"]["bones"],p["bones"]):
                self.assertEqual(a["local_position"],b["local_position"])
        self.assertNotEqual(result["profile"]["sides"]["source"]["leg_alignment"]["directions"],
                            result["profile"]["sides"]["target"]["leg_alignment"]["directions"])
        self.assertEqual(result["acceptance"]["user_review"], "pending")

    def test_stale_pair_and_bind(self):
        inv,models,pair = fixture()
        inv["ops"].append(dict(type="FK",enabled=False))
        with self.assertRaisesRegex(ValueError,"Stale pair"):
            compile_pair(inv,models,pair)
        pair["inventory_sha256"] = fingerprint(inv)
        inv["sides"]["source"]["snapshot"]["bones"][0]["ref_position"] = [1,0,0]
        pair["inventory_sha256"] = fingerprint(inv)
        with self.assertRaisesRegex(ValueError,"Stale model"):
            compile_pair(inv,models,pair)

    def test_model_identity_reusable_across_pose(self):
        inv,models,pair = fixture()
        snap = inv["sides"]["source"]["snapshot"]
        identity = reference_identity(snap)
        snap["bones"][4]["offset"] = axis_angle([1,0,0],5)
        forward(snap["bones"])
        self.assertEqual(identity,reference_identity(snap))
        with self.assertRaisesRegex(ValueError,"Stale pair"):
            compile_pair(inv,models,pair)

    def test_spine_must_not_include_leg_ancestor(self):
        inv,models,_ = fixture()
        m = models["target"]
        m["roles"]["spine"][0] = "bpelvis"
        inv["sides"]["target"]["chains"]["bSpine"] = ["bpelvis","bchest"]
        with self.assertRaisesRegex(ValueError,"leg ancestor"):
            validate_model(m,inv["sides"]["target"])

    def test_bad_limb_mapping(self):
        inv,models,pair = fixture()
        inv["mappings"]["bLL"] = "aRL"
        pair["inventory_sha256"] = fingerprint(inv)
        with self.assertRaisesRegex(ValueError,"chain mapping"):
            compile_pair(inv,models,pair)

    def test_draft_and_unreviewed_cannot_execute(self):
        inv,models,pair = fixture()
        pair["review"]["unresolved"] = ["which deform legs?"]
        with self.assertRaisesRegex(ValueError,"unresolved"):
            compile_pair(inv,models,pair)
        models["target"]["role_evidence"]["legs"] = []
        with self.assertRaisesRegex(ValueError,"role evidence"):
            validate_model(models["target"],inv["sides"]["target"])

    def test_pre_correction_then_solve_and_reject_post_torso_damage(self):
        inv,models,pair = fixture()
        edit = dict(bone="bspine",mode="add_local",axis=[1,0,0],degrees=3)
        decision = pair["sides"]["target"]
        decision["edit_reasons"] = {"bspine":"test slight torso correction"}
        decision["pre_edits"] = [edit]
        compile_pair(inv,models,pair)
        decision["pre_edits"] = []
        # Rotate around up to leave torso tilt unchanged but break arm directions.
        edit.update(axis=[0,0,1],degrees=10)
        decision["edits"] = [edit]
        with self.assertRaisesRegex(ValueError,"broke reviewed"):
            compile_pair(inv,models,pair)

    def test_legacy_scale_rejected(self):
        inv,_,_ = fixture()
        inv["sides"]["target"]["snapshot"]["bones"][0]["ref_scale"] = [100]*3
        with self.assertRaisesRegex(ValueError,"unit bone scale"):
            draft_pair(inv)

    def test_path_and_overwrite_guards(self):
        for bad in ("/Game/A/../B", "/Game", "C:/foo", "/Game/A//B"):
            with self.assertRaises(ValueError): asset_path(bad)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"run"
            write_bundle(path,{"plan.json":{"test":True}})
            with self.assertRaises(FileExistsError): write_bundle(path,{"plan.json":{}})
            self.assertTrue(json.loads((path/"plan.json").read_text())["test"])

    def test_cli_roundtrip(self):
        inv,models,pair = fixture()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_bundle(root/"in",{"inventory.json":inv,"source.json":models["source"],"target.json":models["target"],"pair.json":pair})
            main(["draft","--inventory",str(root/"in/inventory.json"),"--source-id","one","--target-id","two","--output-dir",str(root/"draft")])
            main(["plan","--inventory",str(root/"in/inventory.json"),"--source-model",str(root/"in/source.json"),
                  "--target-model",str(root/"in/target.json"),"--pair",str(root/"in/pair.json"),"--output-dir",str(root/"plan")])
            self.assertTrue((root/"plan/acceptance.json").exists())


if __name__ == "__main__": unittest.main()
