import gurobipy
import io
import traceback
import cobra
from qtpy.QtWidgets import QMessageBox


def except_likely_community_model_error() -> None:
    """Shows a message in the case that using a (size-limited) community edition solver version probably caused an error."""
    community_error_text = "Solver error. One possible reason: You set CPLEX or Gurobi as solver although you only use their\n"+\
                            "Community edition which only work for small models. To solve this, either follow the instructions under\n"+\
                            "'Config->Configure IBM CPLEX full version' or 'Config->Configure Gurobi full version', or use a different solver such as GLPK."
    msgBox = QMessageBox()
    msgBox.setWindowTitle("Error")
    msgBox.setText(community_error_text)
    msgBox.setIcon(QMessageBox.Warning)
    msgBox.exec()


def get_last_exception_string() -> str:
    output = io.StringIO()
    traceback.print_exc(file=output)
    return output.getvalue()


def has_community_error_substring(string: str) -> bool:
    return ("Model too large for size-limited license" in string) or ("1016: Community Edition" in string)


def model_optimization_with_exceptions(model: cobra.Model) -> None:
    try:
        return model.optimize()
    except gurobipy.GurobiError as error:
        msgBox = QMessageBox()
        msgBox.setWindowTitle("Gurobi Error!")
        msgBox.setText("Calculation failed due to the following Gurobi solver error " +\
                       "(if this error cannot be resolved,\ntry using a different solver by changing " +\
                       "it under 'Config->Configure cobrapy'):\n"+error.message+\
                       "\nNOTE: Another error message will follow, you can safely ignore it.")
        msgBox.setIcon(QMessageBox.Warning)
        msgBox.show()
    except Exception:
        exstr = get_last_exception_string()
        # Check for substrings of Gurobi and CPLEX community edition errors
        if has_community_error_substring(exstr):
            except_likely_community_model_error()
