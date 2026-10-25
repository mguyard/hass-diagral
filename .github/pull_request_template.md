<!--
Title: Conventional Commits with a gitmoji, e.g. `fix(sensor): 🐛 Name an anomaly after a device of its own type`.
Target branch: `dev`. See CONTRIBUTING.md.
-->

## Summary

<!-- What changed and why. -->

## Tests

<!-- How it was verified: the pytest summary line, and anything checked by hand. -->

```
python -m pytest custom_components/diagral/tests/
✅ N passed, ❌ 0 failed, ⚠️ 0 errors
```

## Live validation

<!-- How it was checked on a running Home Assistant, and which version. "N/A" with a reason when the change has no runtime effect. -->

## Related issues

<!-- `Refs #N`. Use `Closes #N` only if the issue should close once the change reaches `main`. -->

## Checklist

- [ ] The PR targets `dev`
- [ ] `pytest`, `ruff check` and `ruff format --check` pass locally
- [ ] Every change under `custom_components/diagral/` comes with its tests
- [ ] New strings are in both `en.json` and `fr.json`, and the documentation is updated
- [ ] Every commit is signed
- [ ] No credential, serial number, alarm name, e-mail address or webhook URL in the code, the fixtures or this description
- [ ] An AI assistant helped with this PR, and I have read and understood every line
