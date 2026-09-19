# Jira integration

## Trigger from Jira

wardenIQ exposes an inbound webhook so Jira can drive it:

```
POST /api/integrations/jira/webhook?token=<WEBHOOK_SECRET>
```

In **Jira Automation** → *When issue created/transitioned* → *Send web request* to that
URL with the issue payload. wardenIQ creates a feature from the issue (key → feature key,
summary → name, description → requirement text; Cloud ADF descriptions supported) and
generates its test cases. Because the feature key matches the Jira key, PRs whose
branch/title contain the key auto-link back. Posting results back to Jira is on the roadmap.

---
