# Engineering Onboarding

## Week One Checklist

New engineers should complete the following in their first week:

1. Set up a development environment using the internal setup script
2. Get added to the on-call rotation calendar (observation only for 30 days)
3. Complete the security training module
4. Ship one small change to production

## Code Review Policy

Every pull request requires at least two approvals before merging. One approval
must come from a member of the owning team. Pull requests larger than 400 lines
should be split into smaller changes unless there is a documented reason not to.

Emergency hotfixes may be merged with a single approval, but must be reviewed
retroactively within 24 hours.

## Deployment Windows

Production deploys are allowed Monday through Thursday, between 9:00 AM and
4:00 PM Pacific. No deploys on Friday, weekends, or the day before a company
holiday. This policy exists because incident response coverage is thinner
outside those windows.

## On-Call

On-call shifts run one week at a time, starting Wednesday at 10:00 AM. The
primary on-call engineer is expected to acknowledge pages within 15 minutes
during business hours and within 30 minutes overnight.
