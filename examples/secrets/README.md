# SOPS example

`dummy-secret.yaml` contains only the literal `NOT-A-REAL-PASSWORD`. It is not referenced by the application, chart, or overlays. `dummy-secret.enc.yaml` is a real SOPS 3.13.3 encryption of that document using an age 1.3.2 recipient. The round-trip was verified, then the disposable private key was deleted. The checked-in ciphertext is a format example; generate your own key to repeat the exercise.

With SOPS and age installed, run from the repository root:

```sh
mkdir -p .tools
umask 077
age-keygen -o .tools/demo.agekey
export SOPS_AGE_KEY_FILE="$PWD/.tools/demo.agekey"
recipient=$(age-keygen -y "$SOPS_AGE_KEY_FILE")
sops encrypt --age "$recipient" --encrypted-regex '^(data|stringData)$' \
  examples/secrets/dummy-secret.yaml > .tools/dummy-secret.enc.yaml
sops decrypt .tools/dummy-secret.enc.yaml
```

The final command prints demonstration data only. On Windows, protect the private-key file with an appropriate user-only ACL and use a Windows path for `SOPS_AGE_KEY_FILE` when running native binaries. Never repeat the print-to-terminal step with real credentials.

Only `data` and `stringData` values are encrypted; Kubernetes metadata remains reviewable. Do not commit private keys or decrypted real Secrets. `.tools/`, `*.agekey`, and `*.decrypted.yaml` are ignored. Do not use the example recipient for real credentials: its private key no longer exists.

Production use needs managed recipients, secure key backup, rotation, and a controlled decryption step. Deployment still uses the existing `shop-runtime` Secret; this phase does not configure SOPS decryption in Argo CD.

[SOPS documentation](https://getsops.io/docs/) and [age documentation](https://github.com/FiloSottile/age).
