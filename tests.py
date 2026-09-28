"""Focused unit tests for the safe expression parser."""
import unittest

from server import CalculationError, ExpressionParser, format_number


def calculate(expression: str) -> str:
    return format_number(ExpressionParser(expression).parse())


class ExpressionParserTests(unittest.TestCase):
    def test_basic_operations(self) -> None:
        self.assertEqual(calculate("12+8"), "20")
        self.assertEqual(calculate("8-3"), "5")
        self.assertEqual(calculate("6*7"), "42")
        self.assertEqual(calculate("10/4"), "2.5")

    def test_precedence_parentheses_and_unary_sign(self) -> None:
        self.assertEqual(calculate("1+2*3"), "7")
        self.assertEqual(calculate("(1+2)*3"), "9")
        self.assertEqual(calculate("-5+8"), "3")
        self.assertEqual(calculate("3*-2"), "-6")

    def test_invalid_input_is_rejected(self) -> None:
        for expression in ("", "1+", "(1+2", "1/0", "alert(1)"):
            with self.subTest(expression=expression):
                with self.assertRaises(CalculationError):
                    calculate(expression)


if __name__ == "__main__":
    unittest.main()
