# Fintel Data Format Guide

## Overview

Fintel.io provides various financial data metrics related to stock ownership and market sentiment. This guide helps understand and parse the data.

## Key Metrics

### Short Interest (SI)

**Definition**: Number of shares sold short that have not been covered/closed

**Typical Format**:
- Percentage (e.g., "5.2%")
- Days to cover (e.g., "1.2 days")
- Change from previous period (e.g., "+0.3%" or "-0.8%")

**Interpretation**:
- High SI (>10%): Potential for short squeeze
- Rising SI: Growing bearish sentiment (or squeeze setup)
- Falling SI: Bears covering, potentially bullish

### Institutional Ownership

**Definition**: Percentage of shares held by institutional investors (hedge funds, mutual funds, ETFs, etc.)

**Typical Format**:
- Percentage (e.g., "68.5%")

**Interpretation**:
- High (>80%): Smart money control, potential stability
- Low (<50%): More retail-driven, potentially more volatile
- Directional change: Accumulation (rising) or distribution (falling)

### Insider Ownership

**Definition**: Percentage of shares held by company insiders (executives, directors)

**Typical Format**:
- Percentage (e.g., "2.1%")

**Interpretation**:
- High (>10%): Management alignment with shareholders
- Insider buying signal: Positive catalyst
- Insider selling signal: Potential concern (context matters)

### Options Flow

**Definition**: Recent options trading activity, especially large/whale trades

**Typical Format**:
- Call vs Put volume ratio
- Unusual activity flags
- Sweep/Block trade indicators

**Interpretation**:
- Heavy call buying: Bullish sentiment
- Heavy put buying: Bearish sentiment or hedging
- Unusual large trades: May signal institutional positioning

## Chips Momentum Indicators

### Concentration

**Definition**: How concentrated ownership is among holders

**Typical Format**:
- Top 10 holders percentage
- Number of institutional holders

**Interpretation**:
- High concentration: Few large holders control the stock
- Diverse ownership: More distributed control

### Accumulation/Distribution

**Definition**: Net flow of shares in/out

**Indicators**:
- Recent institutional purchases vs sales
- Ownership percentage trends

## Data Access Methods

### Web Interface
1. Visit `https://fintel.io/s/us/<TICKER>`
2. Navigate to relevant sections:
   - "Short Interest" tab
   - "Ownership" tab
   - "Options" tab

### Manual Data Extraction

When copying data for manual parsing, include:
1. The metric name (e.g., "Short Interest")
2. The numerical value
3. Percentage and unit indicators
4. Any change/trend arrows

**Good Example**:
```
Short Interest: 4.2%
Days to Cover: 1.5 days
Change: +0.8% (↑)

Institutional Ownership: 72.3%
Insider Ownership: 1.8%
```

## Common Data Locations

| Metric | Typical Section on Fintel |
|--------|--------------------------|
| Short Interest | "Short Interest" tab |
| Institutional Ownership | "Ownership" tab |
| Options Flow | "Options" tab, "Flow" section |
| Top Holders | "Ownership" tab, "Top Holders" |

## Limitations

- Data may have a delay (not real-time)
- Some metrics require premium subscription
- Data interpretation requires context from price action
- Different platforms may show slightly different numbers
