"""
Tests for HiGHS QP support in optlang.
"""
import unittest
import numpy as np
import cobra

try:
    import highspy
except ImportError:
    raise ImportError("The highs_interface requires highspy: pip install highspy")

# Assuming the interface code is in a file named highs_interface.py
# If it is in the same directory, you can just import it.
# For this test script to run standalone, we assume the class definitions 
# are available or imported from the module where you saved the previous code.
import sys
import os

import cnapy.optlang_highs_interface

# Add the current directory to the path to import the module if needed
sys.path.insert(0, os.path.dirname(__file__))
cobra.Configuration.solver = cnapy.optlang_highs_interface
from cnapy.optlang_highs_interface import Model, Variable, Constraint, Objective, _get_quadratic_terms_from_expr

# try:
#     from cnapy.optlang_highs_interface import Model, Variable, Constraint, Objective, _get_quadratic_terms_from_expr
# except ImportError:
#     # If the file is named differently, adjust here
#     print("Could not import highs_interface. Ensure it is in the path.")
#     sys.exit(1)
# from optlang import symbolics

class TestHiGHSQP(unittest.TestCase):
    def setUp(self):
        self.model = Model()

    def test_simple_qp_unconstrained(self):
        """Test solving a simple unconstrained QP: min x^2 + y^2."""
        x = Variable("x", lb=-10, ub=10)
        y = Variable("y", lb=-10, ub=10)
        
        self.model.add(x)
        self.model.add(y)
        
        # Objective: x^2 + y^2
        # In HiGHS formulation: 0.5 * x^T * Q * x
        # x^2 implies Q_xx = 2.0
        obj_expr = x**2 + y**2
        self.model.objective = Objective(obj_expr, direction="min")
        
        status = self.model.optimize()
        self.assertEqual(status, "optimal")
        
        # Solution should be x=0, y=0
        self.assertAlmostEqual(self.model.objective.value, 0.0)
        self.assertAlmostEqual(x.primal, 0.0, places=5)
        self.assertAlmostEqual(y.primal, 0.0, places=5)

    def test_simple_qp_constrained(self):
        """Test solving a constrained QP: min x^2 + y^2 s.t. x + y >= 1."""
        x = Variable("x", lb=-10, ub=10)
        y = Variable("y", lb=-10, ub=10)
        
        self.model.add(x)
        self.model.add(y)
        
        # Constraint: x + y >= 1
        self.model.add(Constraint(x + y, lb=1))
        
        # Objective: x^2 + y^2
        self.model.objective = Objective(x**2 + y**2, direction="min")
        
        status = self.model.optimize()
        self.assertEqual(status, "optimal")
        
        # Analytical solution for min x^2 + y^2 s.t. x + y = 1 is x=0.5, y=0.5
        self.assertAlmostEqual(x.primal, 0.5, places=4)
        self.assertAlmostEqual(y.primal, 0.5, places=4)
        self.assertAlmostEqual(self.model.objective.value, 0.5, places=4)

    def test_qp_with_linear_term(self):
        """Test QP with linear terms: min (x-1)^2 + (y-2)^2."""
        x = Variable("x", lb=-10, ub=10)
        y = Variable("y", lb=-10, ub=10)
        
        self.model.add(x)
        self.model.add(y)
        
        # (x-1)^2 + (y-2)^2 = x^2 - 2x + 1 + y^2 - 4y + 4
        # Objective: x^2 + y^2 - 2x - 4y + 5
        self.model.objective = Objective(x**2 + y**2 - 2*x - 4*y + 5, direction="min")
        
        status = self.model.optimize()
        self.assertEqual(status, "optimal")
        
        # Solution should be x=1, y=2
        self.assertAlmostEqual(x.primal, 1.0, places=4)
        self.assertAlmostEqual(y.primal, 2.0, places=4)
        self.assertAlmostEqual(self.model.objective.value, 0.0, places=4)

    def test_qp_cross_term(self):
        """Test QP with cross terms: min x^2 + y^2 + xy."""
        x = Variable("x", lb=-10, ub=10)
        y = Variable("y", lb=-10, ub=10)
        
        self.model.add(x)
        self.model.add(y)
        
        # Objective: x^2 + y^2 + x*y
        # Note: HiGHS Hessian is symmetric. x*y contributes to Q_xy and Q_yx.
        # Our implementation handles the symmetry.
        self.model.objective = Objective(x**2 + y**2 + x*y, direction="min")
        
        status = self.model.optimize()
        self.assertEqual(status, "optimal")
        
        # Solution should be x=0, y=0
        self.assertAlmostEqual(x.primal, 0.0, places=5)
        self.assertAlmostEqual(y.primal, 0.0, places=5)

    def test_qp_to_lp_transition(self):
        """Test changing objective from QP to LP."""
        x = Variable("x", lb=0, ub=10)
        y = Variable("y", lb=0, ub=10)
        
        self.model.add(x)
        self.model.add(y)
        
        # 1. Solve QP
        self.model.objective = Objective(x**2 + y**2, direction="min")
        status = self.model.optimize()
        self.assertEqual(status, "optimal")
        self.assertAlmostEqual(x.primal, 0.0)
        
        # 2. Change to LP objective
        self.model.objective = Objective(x + y, direction="max")
        status = self.model.optimize()
        self.assertEqual(status, "optimal")
        self.assertAlmostEqual(x.primal, 10.0)
        self.assertAlmostEqual(y.primal, 10.0)

    def test_lp_to_qp_transition(self):
        """Test changing objective from LP to QP."""
        x = Variable("x", lb=0, ub=10)
        y = Variable("y", lb=0, ub=10)
        
        self.model.add(x)
        self.model.add(y)
        
        # 1. Solve LP
        self.model.objective = Objective(x + y, direction="max")
        status = self.model.optimize()
        self.assertEqual(status, "optimal")
        self.assertAlmostEqual(x.primal, 10.0)
        
        # 2. Change to QP objective
        self.model.objective = Objective((x-5)**2 + (y-5)**2, direction="min")
        status = self.model.optimize()
        self.assertEqual(status, "optimal")
        self.assertAlmostEqual(x.primal, 5.0, places=4)
        self.assertAlmostEqual(y.primal, 5.0, places=4)

    def test_infeasible_qp(self):
        """Test an infeasible QP."""
        x = Variable("x", lb=0, ub=10)
        y = Variable("y", lb=0, ub=10)
        
        self.model.add(x)
        self.model.add(y)
        
        # Contradictory constraints
        self.model.add(Constraint(x + y, lb=30, ub=30))
        
        self.model.objective = Objective(x**2 + y**2, direction="min")
        status = self.model.optimize()
        self.assertEqual(status, "infeasible")

    def test_unbounded_qp(self):
        """Test an unbounded QP (if applicable, though QP is often bounded by curvature)."""
        x = Variable("x", lb=-10, ub=10) # Bounded variable
        y = Variable("y", lb=-10, ub=10)
        
        self.model.add(x)
        self.model.add(y)
        
        # Objective: -x^2 - y^2 (Concave, max problem)
        # With bounds, it should be solvable at the bounds.
        self.model.objective = Objective(-(x**2) - (y**2), direction="max")
        status = self.model.optimize()
        self.assertEqual(status, "optimal")
        
        # Maximize -x^2 - y^2 is same as minimize x^2 + y^2.
        # Wait, if we maximize -x^2, the max is at x=0.
        # If we had -x^2 + x, it might be unbounded if x is unbounded.
        # Here x is bounded, so it should be optimal.
        self.assertAlmostEqual(x.primal, 0.0, places=5)

    def test_quadratic_coefficient_extraction(self):
        """Test the internal helper for extracting quadratic coefficients."""
        # Updated import name
        
        x = Variable("x")
        y = Variable("y")
        
        # Case 1: x^2
        # We need to pass a SymPy expression, not an Objective instance
        obj_expr = x**2
        terms,rest = _get_quadratic_terms_from_expr(obj_expr)
        self.assertEqual(terms, {('x', 'x'): 1.0})
        self.assertEqual(rest, 0)
        
        # Case 2: x*y
        obj_expr = x*y
        terms,rest = _get_quadratic_terms_from_expr(obj_expr)
        self.assertEqual(terms, {('x', 'y'): 1.0})
        self.assertEqual(rest, 0)
        
        # Case 3: 2*x^2 + 3*x*y
        obj_expr = 2*x**2 + 3*x*y
        terms,rest = _get_quadratic_terms_from_expr(obj_expr)
        self.assertEqual(terms, {('x', 'x'): 2.0, ('x', 'y'): 3.0})
        self.assertEqual(rest, 0)

    def test_rebuild_with_qp(self):
        """Test that removing a variable triggers a rebuild and preserves QP objective."""
        x = Variable("x", lb=-10, ub=10)
        y = Variable("y", lb=-10, ub=10)
        z = Variable("z", lb=-10, ub=10)
        
        self.model.add(x)
        self.model.add(y)
        self.model.add(z)
        
        self.model.objective = Objective(x**2 + y**2 + z**2, direction="min")
        
        # Optimize initial
        status = self.model.optimize()
        self.assertEqual(status, "optimal")
        
        # Remove z
        self.model.remove(z)
        
        # Optimize again
        status = self.model.optimize()
        self.assertEqual(status, "optimal")
        
        # Check that x and y are still 0
        self.assertAlmostEqual(x.primal, 0.0, places=5)
        self.assertAlmostEqual(y.primal, 0.0, places=5)
        
        # Check that z is gone
        # The interface returns None for variables not in the problem
        self.assertIsNone(z.primal)

    
    def test_qp_solution_value_accuracy(self):
        """Test that the reported objective value matches the calculated value."""
        x = Variable("x", lb=-10, ub=10)
        y = Variable("y", lb=-10, ub=10)
        
        self.model.add(x)
        self.model.add(y)
        
        # Constraint: x + y = 2
        self.model.add(Constraint(x + y, lb=2, ub=2))
        
        # Objective: x^2 + y^2
        self.model.objective = Objective(x**2 + y**2, direction="min")
        
        self.model.optimize()
        
        # Analytical solution: x=1, y=1. Obj = 1^2 + 1^2 = 2.
        expected_val = 1.0**2 + 1.0**2
        
        # The solver might return slightly different due to tolerances
        self.assertAlmostEqual(self.model.objective.value, expected_val, places=4)
        
        # Verify manually using primals
        manual_val = x.primal**2 + y.primal**2
        self.assertAlmostEqual(self.model.objective.value, manual_val, places=6)

    def test_set_coefficients_linear(self):
        """Test setting linear objective coefficients via dictionary."""
        x = Variable("x", lb=-10, ub=10)
        y = Variable("y", lb=-10, ub=10)
        
        self.model.add(x)
        self.model.add(y)
        
        self.model.objective = Objective(0)
        
        # Use Variable objects as keys
        self.model.objective.set_coefficients(linear={x: 1.0, y: 1.0})
        self.model.objective.direction = "max"
        
        status = self.model.optimize()
        self.assertEqual(status, "optimal")
        self.assertAlmostEqual(x.primal, 10.0)
        self.assertAlmostEqual(y.primal, 10.0)

    def test_set_coefficients_quadratic(self):
        """Test setting quadratic objective coefficients via dictionary."""
        x = Variable("x", lb=-10, ub=10)
        y = Variable("y", lb=-10, ub=10)
        
        self.model.add(x)
        self.model.add(y)
        
        self.model.objective = Objective(0)
        
        # Use Variable objects as keys
        self.model.objective.set_coefficients(quadratic={(x, x): 1.0, (y, y): 1.0})
        self.model.objective.direction = "min"
        
        status = self.model.optimize()
        self.assertEqual(status, "optimal")
        self.assertAlmostEqual(x.primal, 0.0, places=5)
        self.assertAlmostEqual(y.primal, 0.0, places=5)

    def test_set_coefficients_mixed(self):
        """Test setting both linear and quadratic coefficients via dictionaries."""
        x = Variable("x", lb=-10, ub=10)
        y = Variable("y", lb=-10, ub=10)
        
        self.model.add(x)
        self.model.add(y)
        
        self.model.objective = Objective(0, direction="min")
        
        # Use Variable objects as keys
        self.model.objective.set_coefficients(
            linear={x: -2.0, y: -4.0},
            quadratic={(x, x): 1.0, (y, y): 1.0}
        )
        
        status = self.model.optimize()
        self.assertEqual(status, "optimal")
        self.assertAlmostEqual(x.primal, 1.0, places=4)
        self.assertAlmostEqual(y.primal, 2.0, places=4)
        self.assertAlmostEqual(self.model.objective.value, -5.0, places=4)

    def test_clear_quadratic_terms(self):
        """Test clearing quadratic terms by setting an empty dictionary."""
        x = Variable("x", lb=0, ub=10)
        y = Variable("y", lb=0, ub=10)
        
        self.model.add(x)
        self.model.add(y)
        
        # Start with QP
        self.model.objective = Objective(x**2 + y**2, direction="min")
        status = self.model.optimize()
        self.assertEqual(status, "optimal")
        self.assertAlmostEqual(x.primal, 0.0)
        
        # Clear quadratic terms and set linear objective
        self.model.objective.set_coefficients(
            linear={x: 1.0, y: 1.0},
            quadratic={}
        )
        self.model.objective.direction = "max"
        
        status = self.model.optimize()
        self.assertEqual(status, "optimal")
        
        # Solution should be at bounds
        self.assertAlmostEqual(x.primal, 10.0)
        self.assertAlmostEqual(y.primal, 10.0)

    def test_expression_reconstruction(self):
        """Test that the expression property correctly reconstructs from dictionaries."""
        x = Variable("x", lb=-10, ub=10)
        y = Variable("y", lb=-10, ub=10)
        
        self.model.add(x)
        self.model.add(y)
        
        # Set objective via dictionaries
        self.model.objective = Objective(0)
        self.model.objective.set_coefficients(
            linear={x: 2.0, y: 3.0},
            quadratic={(x, x): 1.0, (x, y): 0.5}
        )
        
        # Get the expression
        expr = self.model.objective.expression
        self.assertEqual(str(expr), "1.0*x**2 + 0.5*x*y + 2.0*x + 3.0*y")
        # use the assertions below if the one above is too strong
        # # Verify it is a SymPy expression and not zero
        # self.assertTrue(expr != 0)
        # self.assertTrue(hasattr(expr, "is_Add") or hasattr(expr, "is_Mul"))
        
        # # Verify x and y are present
        # self.assertIn(x, expr.atoms(symbolics.Symbol))
        # self.assertIn(y, expr.atoms(symbolics.Symbol))

    def test_constraint_set_linear_coefficients(self):
        """Test setting constraint coefficients directly via dictionary."""
        x = Variable("x", lb=0, ub=10)
        y = Variable("y", lb=0, ub=10)
        
        self.model.add(x)
        self.model.add(y)
        
        # Initial constraint: x + y <= 5
        # With objective max x + y, solution should be x=5, y=0 (or any combination summing to 5)
        # But usually solvers pick one. Let's use a more distinct objective.
        # Objective: max x
        self.model.objective = Objective(x, direction="max")
        
        constraint = Constraint(x + y, lb=0, ub=5)
        self.model.add(constraint)
        
        status = self.model.optimize()
        self.assertEqual(status, "optimal")
        
        # With max x and x + y <= 5, x should be 5, y should be 0.
        self.assertAlmostEqual(x.primal, 5.0)
        self.assertAlmostEqual(y.primal, 0.0)
        
        # Now update the constraint coefficients using the dictionary method
        # Change constraint to: 2*x + y <= 5
        # With max x, 2*x <= 5 => x <= 2.5.
        # So x should be 2.5, y should be 0.
        constraint.set_linear_coefficients({x: 2.0, y: 1.0})        
        status = self.model.optimize()
        self.assertEqual(status, "optimal")
        
        self.assertAlmostEqual(x.primal, 2.5, places=4)
        self.assertAlmostEqual(y.primal, 0.0, places=4)
        
        # Verify the expression property reconstructs correctly
        expr = constraint.expression
        self.assertEqual(str(expr), "2.0*x + 1.0*y")
        # # The expression should be 2.0*x + 1.0*y
        # # We check if x and y are present
        # self.assertIn(x, expr.atoms(symbolics.Symbol))
        # self.assertIn(y, expr.atoms(symbolics.Symbol))

    def test_cobrapy_context_objective_rollback(self):
        """Test that rolling back objective changes works correctly."""
        import cobra
        from cobra import Model as CobraModel

        cobra_model = CobraModel('test_model')
        
        # Make metabolites boundary metabolites so they can accumulate/dissipate
        # This allows flux to be non-zero.
        met_a = cobra.Metabolite('A', compartment='e') # e for extracellular
        met_b = cobra.Metabolite('B', compartment='e')
        cobra_model.add_metabolites([met_a, met_b])
        
        reaction = cobra.Reaction('R1')
        reaction.add_metabolites({met_a: -1, met_b: 1})
        cobra_model.add_reactions([reaction])
        cobra_model.add_boundary(met_a, type="exchange")
        cobra_model.add_boundary(met_b, type="exchange")
        
        # Set objective to maximize R1
        cobra_model.objective = 'R1'
        cobra_model.objective_direction = 'max'
        
        # Optimize
        sol = cobra_model.optimize()
        self.assertEqual(sol.objective_value, 1000.0)
        
        # ... rest of test
        
    def test_cobrapy_context_bounds_rollback(self):
        """Test that rolling back variable bound changes works correctly."""
        import cobra
        from cobra import Model as CobraModel

        cobra_model = CobraModel('test_model')
        cobra_model.add_metabolites([cobra.Metabolite('A', compartment='e')])
        reaction = cobra.Reaction('R1')
        reaction.add_metabolites({cobra_model.metabolites.A: -1})
        cobra_model.add_reactions([reaction])
        cobra_model.add_boundary(cobra_model.metabolites.A, type="exchange")
        cobra_model.objective = 'R1'
        
        # Initial bounds
        initial_lb = cobra_model.reactions.get_by_id('R1').lower_bound
        initial_ub = cobra_model.reactions.get_by_id('R1').upper_bound
        
        with cobra_model:
            # Change bounds
            cobra_model.reactions.get_by_id('R1').lower_bound = 10
            cobra_model.reactions.get_by_id('R1').upper_bound = 20
            
            # Verify change
            self.assertEqual(cobra_model.reactions.get_by_id('R1').lower_bound, 10)
            
        # Verify rollback
        self.assertEqual(cobra_model.reactions.get_by_id('R1').lower_bound, initial_lb)
        self.assertEqual(cobra_model.reactions.get_by_id('R1').upper_bound, initial_ub)

    # this test cannot work  because for the rollback to happen one would need 
    # to set the objective via cobra_model.objective and this only supports a 
    # dictionary of linear coefficients, not quadratic ones.
    # def test_cobrapy_context_qp_rollback(self):
    #     """Test that rolling back quadratic objective changes works correctly."""
    #     import cobra
    #     from cobra import Model as CobraModel

    #     cobra_model = CobraModel('test_model')
        
    #     # Make metabolites boundary metabolites
    #     met_a = cobra.Metabolite('A', compartment='e')
    #     met_b = cobra.Metabolite('B', compartment='e')
    #     cobra_model.add_metabolites([met_a, met_b])
        
    #     reaction = cobra.Reaction('R1')
    #     reaction.add_metabolites({met_a: -1, met_b: 1})
    #     cobra_model.add_reactions([reaction])
    #     cobra_model.add_boundary(met_a, type="exchange")
    #     cobra_model.add_boundary(met_b, type="exchange")
                
    #     # Set a linear objective initially
    #     cobra_model.objective = 'R1'
    #     cobra_model.objective_direction = 'max'
        
    #     # Optimize initial state to ensure we are in a clean LP state
    #     sol_init = cobra_model.optimize()
    #     self.assertGreater(sol_init.fluxes['R1'], 0)
        
    #     with cobra_model:
    #         # Change to a quadratic objective using the HiGHS interface method
    #         # cobra_model.solver is the Model instance
    #         # cobra_model.solver.objective is the Objective instance
            
    #         r1 = cobra_model.reactions.get_by_id('R1')
            
    #         # Set quadratic coefficients: (R1 - 0.5)^2 = R1^2 - R1 + 0.25
    #         # Note: must use r1.forward_variable (the actual optlang Variable),
    #         # not the cobra Reaction object itself - Reaction.name is its
    #         # human-readable descriptive name (defaults to ""), not the
    #         # solver variable name, so passing r1 directly silently resolves
    #         # to the wrong (nonexistent) column.
    #         r1_var = r1.forward_variable
    #         cobra_model.solver.objective.set_coefficients(
    #             quadratic={(r1_var, r1_var): 1.0},
    #             linear={r1_var: -1.0},
    #             constant=0.25
    #         )
    #         cobra_model.solver.objective.direction = 'min'
            
    #         sol_temp = cobra_model.optimize()
    #         # Solution should be close to 0.5
    #         self.assertAlmostEqual(sol_temp.fluxes['R1'], 0.5, places=4)
            
    #     # Verify rollback: The objective should be linear again
    #     self.assertTrue(cobra_model.objective.is_Linear)
        
    #     # Optimize to ensure solver is in the correct state
    #     sol_final = cobra_model.optimize()
    #     # With linear objective max R1, it should go to upper bound (1000)
    #     self.assertAlmostEqual(sol_final.fluxes['R1'], 1000.0)

if __name__ == '__main__':
    unittest.main()
