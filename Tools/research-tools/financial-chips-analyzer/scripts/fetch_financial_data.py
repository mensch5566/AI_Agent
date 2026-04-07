#!/usr/bin/env python3
"""
Financial Data Fetcher for Fintel and Barchart

Fetches chips allocation, chips momentum, and Gamma Exposure (GEX) data.
Supports both automated scraping and manual data parsing.
"""

import requests
import json
import sys
from datetime import datetime
from typing import Dict, Optional, Any
import re


class FinancialDataFetcher:
    """Fetch financial data from Fintel and Barchart."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })

    def fetch_fintel_data(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Attempt to fetch data from Fintel.

        Args:
            ticker: Stock ticker symbol (e.g., 'AAPL')

        Returns:
            Dictionary containing chips data or None if failed
        """
        try:
            # Fintel.io endpoints (may need adjustment based on actual site structure)
            # This is a template - actual URLs may require investigation

            # Try short interest page
            si_url = f"https://fintel.io/s/us/{ticker}"
            response = self.session.get(si_url, timeout=10)

            if response.status_code == 200:
                # Parse HTML response to extract data
                # This is a simplified placeholder - actual parsing depends on page structure
                data = {
                    'source': 'fintel',
                    'ticker': ticker,
                    'timestamp': datetime.now().isoformat(),
                    'short_interest': self._parse_short_interest(response.text),
                    'institutional_ownership': self._parse_institutional_ownership(response.text),
                }
                return data

        except Exception as e:
            print(f"Error fetching Fintel data: {e}", file=sys.stderr)

        return None

    def fetch_barchart_data(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Attempt to fetch data from Barchart.

        Args:
            ticker: Stock ticker symbol (e.g., 'AAPL')

        Returns:
            Dictionary containing GEX data or None if failed
        """
        try:
            # Barchart endpoints
            # This is a template - actual URLs may require investigation

            gex_url = f"https://www.barchart.com/stocks/quotes/{ticker}/options"
            response = self.session.get(gex_url, timeout=10)

            if response.status_code == 200:
                data = {
                    'source': 'barchart',
                    'ticker': ticker,
                    'timestamp': datetime.now().isoformat(),
                    'gex': self._parse_gex(response.text),
                }
                return data

        except Exception as e:
            print(f"Error fetching Barchart data: {e}", file=sys.stderr)

        return None

    def parse_manual_data(self, pasted_content: str) -> Dict[str, Any]:
        """
        Parse manually pasted webpage content.

        Args:
            pasted_content: Raw text pasted from webpage

        Returns:
            Dictionary containing parsed data
        """
        data = {
            'source': 'manual',
            'timestamp': datetime.now().isoformat(),
            'raw': pasted_content,
        }

        # Try to detect and extract various metrics
        data.update(self._extract_metrics_from_text(pasted_content))

        return data

    def _parse_short_interest(self, html: str) -> Optional[float]:
        """Extract short interest percentage from HTML."""
        # Pattern matching for short interest
        patterns = [
            r'Short Interest[:\s]*([\d.]+)%',
            r'SI[:\s]*([\d.]+)%',
        ]
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                return float(match.group(1))
        return None

    def _parse_institutional_ownership(self, html: str) -> Optional[float]:
        """Extract institutional ownership percentage from HTML."""
        patterns = [
            r'Institutional Ownership[:\s]*([\d.]+)%',
            r'Inst Own[:\s]*([\d.]+)%',
        ]
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                return float(match.group(1))
        return None

    def _parse_gex(self, html: str) -> Optional[Dict[str, Any]]:
        """Extract GEX metrics from HTML."""
        gex_data = {}

        # Look for GEX values
        gex_match = re.search(r'GEX[:\s]*(-?[\d.,]+)\s*(million|billion)?', html, re.IGNORECASE)
        if gex_match:
            value = float(gex_match.group(1).replace(',', ''))
            if gex_match.group(2) == 'billion':
                value *= 1000
            gex_data['total_gex'] = value

        # Try to detect positive/negative
        if 'positive' in html.lower() and 'gex' in html.lower():
            gex_data['direction'] = 'positive'
        elif 'negative' in html.lower() and 'gex' in html.lower():
            gex_data['direction'] = 'negative'

        return gex_data if gex_data else None

    def _extract_metrics_from_text(self, text: str) -> Dict[str, Any]:
        """Extract financial metrics from pasted text."""
        metrics = {}

        # Common patterns
        patterns = {
            'short_interest': r'(?:Short Interest|SI)[:\s]*([\d.]+)%',
            'institutional_ownership': r'(?:Institutional Ownership|Inst Own)[:\s]*([\d.]+)%',
            'insider_ownership': r'(?:Insider Ownership|Insider Own)[:\s]*([\d.]+)%',
            'gex': r'GEX[:\s]*(-?[\d.,]+)\s*(million|billion)?',
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = float(match.group(1).replace(',', ''))
                if len(match.groups()) > 1 and match.group(2) == 'billion':
                    value *= 1000
                metrics[key] = value

        return metrics


def main():
    """Main entry point for command-line usage."""
    if len(sys.argv) < 2:
        print(json.dumps({
            'error': 'No ticker provided',
            'usage': 'python fetch_financial_data.py <TICKER> [--manual]'
        }))
        sys.exit(1)

    ticker = sys.argv[1].upper()
    manual = '--manual' in sys.argv

    fetcher = FinancialDataFetcher()

    if manual:
        # Manual mode - prompt for data input
        print("Please paste the webpage content (Ctrl+D to finish):")
        content = sys.stdin.read()
        result = fetcher.parse_manual_data(content)
    else:
        # Automated mode - try to fetch
        fintel_data = fetcher.fetch_fintel_data(ticker)
        barchart_data = fetcher.fetch_barchart_data(ticker)

        result = {
            'ticker': ticker,
            'timestamp': datetime.now().isoformat(),
            'fintel': fintel_data,
            'barchart': barchart_data,
        }

        # Check if we got any data
        if not fintel_data and not barchart_data:
            result['error'] = 'Could not fetch automated data. Manual input required.'
            result['manual_mode_available'] = True

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
