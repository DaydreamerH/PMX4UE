"""Exact-path screenshot retention; never touch source images or UE assets."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

CAPTURE = re.compile(r"PMX4UE_([a-f0-9]{32})_[0-9]{4,}\.png\Z")
TEXT_SUFFIXES = {'.json', '.md', '.txt', '.log'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def ordinary(path, root):
    path, root = Path(path).absolute(), Path(root).absolute()
    if not path.is_relative_to(root) or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Path is outside the managed root: ' + str(path))
    for part in (path, *path.parents):
        info = part.lstat()
        if part.is_symlink() or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Symlink/junction/reparse point is not allowed: ' + str(part))
        if part == root:
            break
    return path.resolve()


def normalize(text):
    return str(text).replace('\\', '/').casefold()


def remove_native_duplicate(project_dir, native, retained, token, digest):
    """Only remove this run's native duplicate after the retained bytes match."""
    project_dir, native, retained = map(Path, (project_dir, native, retained))
    match = CAPTURE.fullmatch(native.name)
    if not match or match[1] != token or native.name != retained.name:
        raise ValueError('Not this preview run\'s exact screenshot')
    if native.parent not in {project_dir/'Saved/PMX4UECaptures', project_dir/'Saved/MMD2UECaptures'}:
        raise ValueError('Unexpected native capture directory')
    native = ordinary(native, project_dir/'Saved')
    retained = ordinary(retained, project_dir/'Saved/PMX4UE')
    if retained.parent.name != 'captures_' + token or native == retained:
        raise ValueError('Unexpected retained capture directory')
    if sha(native) != digest or sha(retained) != digest:
        raise ValueError('Both screenshot copies must match the retained evidence hash')
    size = native.stat().st_size
    try:
        native.unlink()  # A single exact, verified duplicate; never a directory.
    except OSError as error:
        return dict(status='duplicate_retained_cleanup_failed', bytes=0, error=str(error))
    return dict(status='removed_verified_native_duplicate', bytes=size, sha256=digest)


def make_plan(policy, _owned_lock=False):
    if policy.get('schema') != 'pmx4ue.capture-retention.v1':
        raise ValueError('Expected screenshot retention policy v1')
    project = Path(policy['project']).absolute()
    if project.suffix.lower() != '.uproject' or not project.is_file():
        raise ValueError('Existing target .uproject required')
    base = project.parent/'Saved/PMX4UE'
    ordinary(base, project.parent)
    root = ordinary(policy['artifact_root'], base)
    if root == base or not root.is_dir():
        raise ValueError('Use a character/version artifact root, not all Saved/PMX4UE')
    if (base/'.agent.lock').exists() and not _owned_lock:
        raise ValueError('Pause workflow execution before planning screenshot cleanup')
    retired, images = {}, {}
    for row in policy.get('retired_records', []):
        path = ordinary(row['path'], root)
        if path.suffix.lower() != '.json' or sha(path) != row['sha256'] or not row.get('reason', '').strip():
            raise ValueError('Retired record needs its current hash and a reason')
        report = read(path)
        capture_report = report.get('schema') == 'pmx4ue.material-captures.v1'
        preview_run = report.get('stage') == 'material-preview' and isinstance(report.get('capture_sha256'), dict)
        if not (capture_report or preview_run) or path in retired:
            raise ValueError('Only distinct preview capture reports/run records may be retired')
        retired[path] = dict(sha256=row['sha256'], reason=row['reason'])
        if capture_report:
            for capture in report.get('captures', []):
                image = capture['image']
                filename = ordinary(image['path'], root)
                match = CAPTURE.fullmatch(filename.name)
                if (not match or filename.parent != path.parent/('captures_' + match[1]) or
                        sha(filename) != image['sha256']):
                    raise ValueError('Only unchanged, registered managed captures can be candidates')
                images.setdefault(filename, dict(sha256=image['sha256'], bytes=filename.stat().st_size,
                                                 owners=[]))['owners'].append(str(path))
    if not retired:
        raise ValueError('Explicitly retire preview records; age alone is not a reason')
    protected = [ordinary(path, project.parent) for path in policy.get('protected_paths', [])]
    scan_roots = [base, *[Path(path).absolute() for path in policy.get('external_reference_roots', [])]]
    documents = {}
    for scan in scan_roots:
        if not scan.exists():
            raise ValueError('Reference scan root is missing: ' + str(scan))
        paths = [scan] if scan.is_file() else scan.rglob('*')
        for path in paths:
            if path.suffix.lower() not in TEXT_SUFFIXES or not path.is_file():
                continue
            if '_capture_retention' in path.parts:
                continue  # Plans/approvals/receipts are bookkeeping, not live evidence.
            path = ordinary(path, scan if scan.is_dir() else scan.parent)
            if path in retired and not any(path == pin or path.is_relative_to(pin) for pin in protected):
                continue
            content = path.read_text(encoding='utf-8-sig')
            if path.suffix.lower() == '.json':
                content = json.dumps(json.loads(content), ensure_ascii=False)
                content = content.replace('\\\\', '\\')
            documents[path] = (sha(path), normalize(content))
    eligible, kept = [], []
    for path, data in sorted(images.items()):
        reasons = []
        owners = [Path(owner) for owner in data['owners']]
        if any(path == pin or path.is_relative_to(pin) or any(owner == pin for owner in owners)
               for pin in protected):
            reasons.append('explicitly_protected')
        needles = [normalize(path), data['sha256'], *[normalize(owner) for owner in owners],
                   *[retired[owner]['sha256'] for owner in owners]]
        # Relative image/report names are intentionally conservative too.
        needles += [path.name.casefold(), *[normalize(owner.relative_to(base)) for owner in owners]]
        for document, (_, content) in documents.items():
            if any(needle in content for needle in needles):
                reasons.append('referenced_by:' + str(document))
        row = dict(path=str(path), **data)
        if reasons:
            kept.append(dict(row, protection=reasons))
        else:
            eligible.append(row)
    return dict(schema='pmx4ue.capture-retention-plan.v1', status='review_required_no_deletion',
                policy=policy, retired_records={str(p): v for p, v in retired.items()},
                reference_sha256={str(p): data[0] for p, data in sorted(documents.items())},
                candidates=eligible, protected=kept, reclaimable_bytes=sum(r['bytes'] for r in eligible))


def output_path(path, root):
    path, root = Path(path).absolute(), Path(root).absolute()
    if not path.is_relative_to(root/'_capture_retention') or path.exists():
        raise ValueError('Use a new output under artifact_root/_capture_retention')
    existing = path.parent
    while not existing.exists():
        existing = existing.parent
    ordinary(existing, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    ordinary(path.parent, root)
    return path


def write_new(path, value):
    path = Path(path)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def apply_plan(plan_path, approval_path, receipt_path):
    plan, approval = read(plan_path), read(approval_path)
    if (approval.get('plan_sha256') != sha(plan_path) or not approval.get('approved_by', '').strip()
            or not approval.get('authorization_basis', '').strip()):
        raise ValueError('A user-authorized exact-plan approval is required')
    if plan != make_plan(plan['policy']):
        raise ValueError('Inputs/references changed; create and approve a new plan')
    root = Path(plan['policy']['artifact_root']).absolute()
    # Reuse the runner lock, then repeat the full reference/file check under it.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from pmx4ue import project_lock
    project = Path(plan['policy']['project']).absolute()
    with project_lock(project):
        if plan != make_plan(plan['policy'], _owned_lock=True):
            raise ValueError('Inputs/references changed under lock; approve a new plan')
        receipt_path = output_path(receipt_path, root)
        receipt = dict(schema='pmx4ue.capture-retention-receipt.v1', status='started',
                       plan_path=str(Path(plan_path).resolve()), plan_sha256=sha(plan_path),
                       retired_records=plan['retired_records'], deleted=[], errors=[], freed_bytes=0,
                       note='Retired reports with missing captures are historical, not valid visual evidence.')
        write_new(receipt_path, receipt)
        for row in plan['candidates']:
            try:
                filename = ordinary(row['path'], root)
                if sha(filename) != row['sha256']:
                    raise ValueError('Candidate changed during cleanup')
                filename.unlink()
                receipt['deleted'].append(row)
                receipt['freed_bytes'] += row['bytes']
            except (OSError, ValueError) as error:
                receipt['errors'].append(dict(path=row['path'], error=str(error)))
                break  # Stop at first failure; retain the partial-operation journal.
            finally:
                receipt['status'] = 'partial_failure' if receipt['errors'] else 'in_progress'
                receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
        receipt['status'] = 'partial_failure' if receipt['errors'] else 'completed'
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
        return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    plan = sub.add_parser('plan')
    plan.add_argument('--policy', required=True)
    plan.add_argument('--output', required=True)
    apply = sub.add_parser('apply')
    apply.add_argument('--plan', required=True)
    apply.add_argument('--approval', required=True)
    apply.add_argument('--receipt', required=True)
    args = parser.parse_args()
    if args.command == 'plan':
        result = make_plan(read(args.policy))
        output = output_path(args.output, result['policy']['artifact_root'])
        write_new(output, result)
    else:
        result = apply_plan(args.plan, args.approval, args.receipt)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get('status') == 'partial_failure':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
