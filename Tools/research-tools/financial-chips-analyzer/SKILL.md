---
name: financial-chips-analyzer
description: Analyze stock chips allocation, chips momentum, and Gamma Exposure (GEX) metrics from financial data platforms like Fintel and Barchart. Generate comprehensive data reports with visualization and interpretation. Use when user mentions stock codes, chips analysis, GEX, Gamma Exposure, Fintel, or Barchart.
---

# Financial Chips Analyzer

Analyze stock chips allocation, chips momentum, and Gamma Exposure (GEX) metrics to provide comprehensive financial data reports.

## When to Use

Trigger this skill when user:
- Provides a stock code (ticker symbol)
- Mentions "chips", "shares allocation", "chip momentum"
- Asks about GEX or Gamma Exposure
- References Fintel or Barchart data

## Workflow

### 1. Identify Stock Code

Extract the stock ticker symbol from user input. Common formats:
- Uppercase: "AAPL", "NVDA", "MSFT"
- With prefix: "stock AAPL", "check AAPL chips"

### 2. Fetch Data

**Priority 1: Automated Scraping**
Use the Python script at `scripts/fetch_financial_data.py` to attempt automated data retrieval:

```bash
python scripts/fetch_financial_data.py <STOCK_CODE>
```

The script will:
- Attempt to fetch data from Fintel
- Attempt to fetch data from Barchart
- Return JSON with chips allocation, momentum, and GEX data
- Handle errors gracefully

**Priority 2: Manual Fallback**
If automated scraping fails:
1. Ask user to visit the relevant webpage
2. Request user to copy/paste the relevant data section
3. Parse the pasted content to extract required metrics

### 3. Extract Key Metrics

From the data, identify:

**Chips Allocation:**
- Institutional ownership percentage
- Retail ownership percentage
- Insider ownership
- Major holders breakdown

**Chips Momentum:**
- Short interest changes
- Options flow
- Recent accumulation/distribution patterns

**Gamma Exposure (GEX):**
- Total GEX level (support/resistance indication)
- GEX per strike price
- Call vs Put GEX balance
- GEX change trends

### 4. Analyze and Interpret

Use `references/gex-explainer.md` for GEX interpretation guidance:

**General Rules:**
- **High Positive GEX**: Market makers are net long calls → acts as support
- **High Negative GEX**: Market makers are net long puts → acts as resistance
- **GEX Flip**: Changing from positive to negative (or vice versa) → potential volatility

**Chips Analysis:**
- Concentration indicates stronger hands controlling the stock
- Divergence between chips and price suggests potential reversal
- Momentum shifts in chips often precede price moves

### 5. Generate Report

Format the output as a structured report:

```
## [Stock Code] Financial Chips Analysis

### Chips Allocation
- Institutional: X%
- Retail: Y%
- Insider: Z%
- Concentration: [High/Medium/Low]

### Chips Momentum
- Recent flow: [Accumulation/Distribution]
- Short interest: X% (↑↓ Y% from last period)
- Options flow: [Bullish/Bearish/Neutral]

### Gamma Exposure
- Total GEX: [Positive/Negative] $X million
- GEX Level: [Support/Resistance zone]
- Call/Put Ratio: X:Y

### Analysis Summary
[Interpret the data - 2-3 sentences on what it means for the stock]
```

### 6. Provide Visualization

When possible, create simple ASCII or text-based visualizations:

**GEX Profile:**
```
GEX by Strike:
          $120  |█████████|  Positive (Support)
          $130  |████|       Neutral
          $140  |███|        Negative (Resistance)
```

**Chips Distribution:**
```
Ownership:
█████████████  Institutional (65%)
███           Retail          (20%)
██            Insider         (15%)
```

## Error Handling

If data cannot be retrieved:
1. Clearly state what data is unavailable
2. Suggest alternative sources or methods
3. Offer to retry with manual data input

## Important Notes

- **Quality over speed**: Ensure data accuracy, double-check parsing
- **Real-time context**: Financial data is time-sensitive, note data timestamps
- **Mixed approach**: Always try automation first, fall back to manual input gracefully
- **User experience**: Guide users through any manual steps clearly

## References

- GEX interpretation: `references/gex-explainer.md`
- Data format guide: `references/fintel-guide.md`
