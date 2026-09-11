"""Safe expression evaluator for ABAC conditions.

Replaces eval() with a restricted evaluator that only allows attribute access,
comparisons, logical operators, and membership tests.
"""

import ast
from typing import Any

# Allowed attribute names for each object type (by class name)
ALLOWED_ATTRIBUTES = {
    "Subject": {"user_id", "role", "scopes", "tenant_id", "department", "clearance", "groups", "is_admin"},
    "Resource": {"type", "id", "owner_id", "tenant_id", "classification", "visibility", "tags"},
    "Environment": {"timestamp", "client_ip", "method", "path"},
}

# Allowed built-in constants
ALLOWED_BUILTINS = {"True", "False", "None"}

# Allowed operators
ALLOWED_OPS = {
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
    ast.And,
    ast.Or,
    ast.Not,
}


class SafeEvalError(Exception):
    """Raised when an expression is not safe to evaluate."""

    pass


class _SafeEvaluator(ast.NodeVisitor):
    """AST visitor that evaluates safe expressions."""

    def __init__(self, namespace: dict[str, Any]):
        self.namespace = namespace

    def eval(self, expression: str) -> Any:
        """Evaluate a safe expression."""
        try:
            tree = ast.parse(expression, mode="eval")
        except SyntaxError as e:
            raise SafeEvalError(f"Syntax error: {e}") from e

        # Check that the expression is safe
        self._check_node(tree.body)

        # Evaluate
        return self._eval_node(tree.body)

    def _check_node(self, node: ast.AST) -> None:
        """Recursively check that a node is safe."""
        if isinstance(node, ast.Expression):
            self._check_node(node.body)
        elif isinstance(node, ast.Constant):
            # Allow constants (True, False, None, strings, numbers)
            if isinstance(node.value, str):
                # String constants are allowed
                pass
            elif isinstance(node.value, (int, float)):
                # Numeric constants are allowed
                pass
            elif node.value in (True, False, None):
                # Boolean and None constants are allowed
                pass
            else:
                raise SafeEvalError(f"Unsafe constant: {node.value}")
        elif isinstance(node, ast.Name):
            # Allow variable names in namespace
            if node.id not in self.namespace and node.id not in ALLOWED_BUILTINS:
                raise SafeEvalError(f"Unknown variable: {node.id}")
        elif isinstance(node, ast.Attribute):
            # Allow attribute access on objects
            self._check_node(node.value)
            # Check that the attribute is allowed for the object type
            if isinstance(node.value, ast.Name):
                obj_name = node.value.id
                if obj_name in self.namespace:
                    obj = self.namespace[obj_name]
                    obj_type = type(obj).__name__
                    if obj_type in ALLOWED_ATTRIBUTES:
                        if node.attr not in ALLOWED_ATTRIBUTES[obj_type]:
                            raise SafeEvalError(f"Attribute {node.attr} not allowed on {obj_type}")
        elif isinstance(node, ast.Compare):
            # Allow comparisons
            self._check_node(node.left)
            for comparator in node.comparators:
                self._check_node(comparator)
            for op in node.ops:
                if type(op) not in ALLOWED_OPS:
                    raise SafeEvalError(f"Operator {type(op).__name__} not allowed")
        elif isinstance(node, ast.BoolOp):
            # Allow boolean operations (and, or)
            if type(node.op) not in ALLOWED_OPS:
                raise SafeEvalError(f"Operator {type(node.op).__name__} not allowed")
            for value in node.values:
                self._check_node(value)
        elif isinstance(node, ast.UnaryOp):
            # Allow unary not
            if type(node.op) not in ALLOWED_OPS:
                raise SafeEvalError(f"Operator {type(node.op).__name__} not allowed")
            self._check_node(node.operand)
        elif isinstance(node, ast.Tuple):
            # Allow tuple literals (used in `act in ("read", "search")`)
            for elt in node.elts:
                self._check_node(elt)
        elif isinstance(node, ast.List):
            # Allow list literals
            for elt in node.elts:
                self._check_node(elt)
        elif isinstance(node, ast.Set):
            # Allow set literals
            for elt in node.elts:
                self._check_node(elt)
        elif isinstance(node, ast.Call):
            # Allow 'in' operator (which is a method call in AST)
            # Actually 'in' is a Compare node, not a Call
            raise SafeEvalError("Function calls not allowed")
        else:
            raise SafeEvalError(f"Unsafe node type: {type(node).__name__}")

    def _eval_node(self, node: ast.AST) -> Any:
        """Evaluate an AST node."""
        if isinstance(node, ast.Expression):
            return self._eval_node(node.body)
        elif isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Name):
            if node.id in ALLOWED_BUILTINS:
                # Evaluate built-in constants
                if node.id == "True":
                    return True
                elif node.id == "False":
                    return False
                elif node.id == "None":
                    return None
            return self.namespace[node.id]
        elif isinstance(node, ast.Attribute):
            obj = self._eval_node(node.value)
            return getattr(obj, node.attr)
        elif isinstance(node, ast.Compare):
            left = self._eval_node(node.left)
            result = True
            for op, comparator in zip(node.ops, node.comparators):
                right = self._eval_node(comparator)
                if isinstance(op, ast.Eq):
                    cmp_result = left == right
                elif isinstance(op, ast.NotEq):
                    cmp_result = left != right
                elif isinstance(op, ast.Lt):
                    cmp_result = left < right
                elif isinstance(op, ast.LtE):
                    cmp_result = left <= right
                elif isinstance(op, ast.Gt):
                    cmp_result = left > right
                elif isinstance(op, ast.GtE):
                    cmp_result = left >= right
                elif isinstance(op, ast.In):
                    cmp_result = left in right
                elif isinstance(op, ast.NotIn):
                    cmp_result = left not in right
                else:
                    raise SafeEvalError(f"Unsupported operator: {type(op).__name__}")

                result = result and cmp_result
                left = right  # For chained comparisons
            return result
        elif isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                result = True
                for value in node.values:
                    result = result and self._eval_node(value)
                    if not result:
                        return False
                return True
            elif isinstance(node.op, ast.Or):
                for value in node.values:
                    if self._eval_node(value):
                        return True
                return False
        elif isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.Not):
                return not self._eval_node(node.operand)
        elif isinstance(node, ast.Tuple):
            return tuple(self._eval_node(elt) for elt in node.elts)
        elif isinstance(node, ast.List):
            return [self._eval_node(elt) for elt in node.elts]
        elif isinstance(node, ast.Set):
            return {self._eval_node(elt) for elt in node.elts}
        else:
            raise SafeEvalError(f"Unsupported node type: {type(node).__name__}")


def safe_eval(expression: str, namespace: dict[str, Any]) -> Any:
    """Safely evaluate an expression with the given namespace.

    Args:
        expression: Python expression string to evaluate
        namespace: Dictionary of variables available in the expression

    Returns:
        The result of evaluating the expression

    Raises:
        SafeEvalError: If the expression contains unsafe operations
    """
    evaluator = _SafeEvaluator(namespace)
    return evaluator.eval(expression)
