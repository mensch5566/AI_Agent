# NLM "Topic - Parse_SEC_Filings" — CF cash begin/end (SEC EFM authority)
Source: a146d037 (SEC EDGAR Financial Report Manual). Notebook 03ef6143.

KEY: EFM §6.8.12 forbids separate begin/end concepts — "same instant = end of one
period AND beginning of the next." Vendors do MOVEMENT ANALYSIS (§7.7): store ONE
instant; renderer shows it as ending(P) and beginning(P+1). Cash = instant → NEVER
subtract; single-quarter beginning = prior quarter's ending instant. Resolver must
match instant DATE to duration start/end (Midnight Rule §9.7), not pick blindly.
Validation: "instant without matching duration" — periodStart instant must match a
duration startDate. => Approach X (store twins) is an EFM anti-pattern; fix in the
display-layer renderer.
