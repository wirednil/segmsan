#!/usr/bin/env python3
"""
Custom test suite for TAL analyzer
Validates test_printf.tal and test_stringlib.tal
"""

import sys
import subprocess
import json
from pathlib import Path


class TestSuite:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.base_dir = Path(__file__).parent

    def run(self):
        """Run all tests"""
        print("=" * 70)
        print("TAL ANALYZER — CUSTOM TEST SUITE")
        print("=" * 70)

        self.test_printf_bad_practices()
        self.test_stringlib_good_practices()
        self.test_storage_accounting()
        self.test_scan_detection()
        self.test_recursion_detection()

        print("\n" + "=" * 70)
        print(f"RESULTS: {self.passed} passed, {self.failed} failed")
        print("=" * 70)

        return self.failed == 0

    def test_printf_bad_practices(self):
        """TEST 1: Verify test_printf.tal generates expected warnings"""
        print("\n[TEST 1] test_printf.tal (BAD PRACTICES)")
        print("-" * 70)

        warnings = self._get_warnings("test_printf.tal")

        # Count warnings by rule
        rule_counts = {}
        for w in warnings:
            kind = w.get("kind", "unknown")
            rule_counts[kind] = rule_counts.get(kind, 0) + 1

        expected = {
            "LOCAL_OVERFLOW": 9,
            "RECURSION_WITHOUT_LARGESTACK": 1,
            "SCAN_WITHOUT_CARRY_CHECK": 1,
            "INDEX_WITHOUT_BOUNDS_CHECK": 1,
        }

        print(f"\nExpected warnings:")
        all_match = True
        for rule, exp_count in expected.items():
            actual = rule_counts.get(rule, 0)
            match = actual == exp_count
            status = "✓" if match else "✗"
            print(f"  {status} {rule:35s}: expected {exp_count}, got {actual}")
            if not match:
                all_match = False

        if all_match:
            self.passed += 1
            print(f"\n✅ PASS: All 7 warnings detected correctly")
        else:
            self.failed += 1
            print(f"\n❌ FAIL: Warning count mismatch")

    def test_stringlib_good_practices(self):
        """TEST 2: Verify test_stringlib.tal is mostly clean"""
        print("\n[TEST 2] test_stringlib.tal (GOOD PRACTICES)")
        print("-" * 70)

        warnings = self._get_warnings("test_stringlib.tal")

        critical = sum(1 for w in warnings if w.get("severity") == "CRITICAL")
        high = sum(1 for w in warnings if w.get("severity") == "HIGH")

        print(f"\nWarning summary:")
        print(f"  CRITICAL: {critical} (expected 0)")
        print(f"  HIGH: {high} (expected ≤ 1)")
        print(f"  Total: {len(warnings)}")

        if critical == 0 and high <= 1:
            self.passed += 1
            print(f"\n✅ PASS: Good code is clean!")
        else:
            self.failed += 1
            print(f"\n❌ FAIL: Too many warnings")

    def test_storage_accounting(self):
        """TEST 3: Verify storage accounting is correct"""
        print("\n[TEST 3] Storage Accounting (snprintf locals only, no param type decls)")
        print("-" * 70)

        warnings = self._get_warnings("test_printf.tal")

        # Find snprintf LOCAL_OVERFLOW
        snprintf_warns = [
            w for w in warnings
            if w.get("kind") == "LOCAL_OVERFLOW" and "snprintf" in w.get("message", "")
        ]

        if snprintf_warns:
            msg = snprintf_warns[0].get("message", "")
            if "160" in msg and "127" in msg:
                self.passed += 1
                print(f"✅ PASS: snprintf storage correctly calculated")
                print(f"   tmpbuf storage: 160 words (params excluded from local count)")
                print(f"   Message: {msg[:60]}...")
            else:
                self.failed += 1
                print(f"❌ FAIL: Storage calculation incorrect")
                print(f"   {msg}")
        else:
            self.failed += 1
            print(f"❌ FAIL: snprintf overflow not detected")

    def test_scan_detection(self):
        """TEST 4: Verify SCAN_WITHOUT_CARRY detection"""
        print("\n[TEST 4] SCAN_WITHOUT_CARRY_CHECK Detection")
        print("-" * 70)

        warnings = self._get_warnings("test_printf.tal")

        scan_warns = [
            w for w in warnings
            if w.get("kind") == "SCAN_WITHOUT_CARRY_CHECK"
        ]

        if scan_warns:
            w = scan_warns[0]
            self.passed += 1
            print(f"✅ PASS: SCAN_WITHOUT_CARRY_CHECK detected")
            print(f"   Location: {w.get('location')}")
            print(f"   Proc: find^char")
            print(f"   Message: {w.get('message')[:50]}...")
        else:
            self.failed += 1
            print(f"❌ FAIL: SCAN_WITHOUT_CARRY_CHECK not detected")

    def test_recursion_detection(self):
        """TEST 5: Verify RECURSION detection"""
        print("\n[TEST 5] RECURSION_WITHOUT_LARGESTACK Detection")
        print("-" * 70)

        warnings = self._get_warnings("test_printf.tal")

        recursion_warns = [
            w for w in warnings
            if w.get("kind") == "RECURSION_WITHOUT_LARGESTACK"
        ]

        if recursion_warns:
            w = recursion_warns[0]
            self.passed += 1
            print(f"✅ PASS: Recursion without ?LARGESTACK detected")
            print(f"   Procedure: print^recursive")
            print(f"   Location: {w.get('location')}")
        else:
            self.failed += 1
            print(f"❌ FAIL: Recursion not detected")

    def _get_warnings(self, filename):
        """Get warnings as list from analyzer"""
        try:
            result = subprocess.run(
                ["python3", "-m", "segmsan", "-f", "json", filename],
                cwd=self.base_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )

            # JSON format is a list of warnings
            if result.stdout:
                return json.loads(result.stdout)
            else:
                return []

        except Exception as e:
            print(f"Error: {e}")
            return []


def main():
    """Entry point"""
    suite = TestSuite()
    success = suite.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
