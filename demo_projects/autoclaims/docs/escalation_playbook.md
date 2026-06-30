# Escalation Playbook

Escalate a claim to `manual_review` when one of these signals is present:

- fraudFlag is true
- claim amount is greater than or equal to 5000 USD
- police report is pending
- customer documents are incomplete for high-value equipment claims

For escalations, add a note naming the blocking signal and the next human owner
action.

