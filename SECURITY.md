# Security

JevDroid is an early alpha automation framework. Treat enabled actions as real
device capabilities. A model may choose an undesirable action within its allowed
set; package allowlists are not semantic authorization for every app control.

Do not include credentials or private device data in public issues. For a
sensitive vulnerability, use GitHub's private vulnerability reporting feature
if enabled on this repository. Otherwise contact the maintainer privately before
publishing reproduction details involving secrets or personal data.

The default traces exclude UI content and credentials. Explicit `inspect` output
and custom event sinks are the operator's responsibility. Provider requests do
send goal and visible accessibility text to the selected service.
