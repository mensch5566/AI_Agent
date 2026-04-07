# Gamma Exposure (GEX) Guide

## What is GEX?

Gamma Exposure (GEX) represents the total gamma exposure of market makers for a given stock. It measures how sensitive market makers are to price movements.

## Key Concepts

### Positive GEX (Support)

- **Definition**: Net long calls vs puts for market makers
- **Mechanism**: As price drops toward call strikes, market makers must sell shares to hedge, creating buying pressure
- **Effect**: Acts as price support, dampens volatility
- **Visual**: Think of it as a "floor" under the stock price

### Negative GEX (Resistance)

- **Definition**: Net long puts vs calls for market makers
- **Mechanism**: As price rises toward put strikes, market makers must buy shares to hedge, creating selling pressure
- **Effect**: Acts as price resistance, can accelerate moves
- **Visual**: Think of it as a "ceiling" above the stock price

### GEX Flip

- **Definition**: When GEX changes from positive to negative (or vice versa)
- **Significance**: Often precedes increased volatility or trend changes
- **Trading Implication**: Monitor stocks approaching GEX flip zones

## Interpretation Framework

| GEX Level | Interpretation |
|-----------|----------------|
| High Positive (+$100M+) | Strong support, low volatility expected |
| Slightly Positive (+$10M to +$100M) | Mild support, moderate volatility |
| Near Zero (-$10M to +$10M) | Neutral, price action dominated by other factors |
| Slightly Negative (-$10M to -$100M) | Mild resistance, can accelerate moves |
| Highly Negative (-$100M+) | Strong resistance potential, high volatility risk |

## GEX by Strike Price

When analyzing GEX distribution:

1. **Identify GEX Walls**: Strike prices with very high GEX values
2. **Support Zones**: Strikes with high positive GEX below current price
3. **Resistance Zones**: Strikes with high negative GEX above current price
4. **GEX Flip Zones**: Strikes where GEX crosses from positive to negative

## Common Patterns

### Call Wall
- Large positive GEX at a call strike above current price
- Price tends to get "stuck" below this level
- Often corresponds to large open interest in OTM calls

### Put Wall
- Large negative GEX at a put strike below current price
- Price can accelerate down if price breaks below
- Often corresponds to large open interest in OTM puts

## Limitations

- GEX is not a perfect predictor
- Other factors (earnings, macro events) can override GEX effects
- GEX can change rapidly with new option positions
- Real-time GEX requires live options data

## Integration with Chips Analysis

Combine GEX with chips data for better insights:

1. **Bullish Setup**: Positive GEX + Chips accumulation
2. **Bearish Setup**: Negative GEX + Chips distribution
3. **Divergence Watch**: GEX suggests one direction, chips suggest another → potential reversal
