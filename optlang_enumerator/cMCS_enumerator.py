import numpy
import cobra
import cobra.util.array
import cobra.io
import optlang.cplex_interface
import optlang.glpk_interface
from optlang.symbolics import add, mul
from optlang.exceptions import IndicatorConstraintsNotSupported
from swiglpk import glp_write_lp

# exec(open('cMCS_enumerator.py').read())

class ConstrainedMinimalCutSetsEnumerator:
    def __init__(self, optlang_interface, st, reversible, targets, kn=None, cuts=None,
        desired= [], knock_in=[], bigM=0, threshold=1, split_reversible_v=True,
        reduce_constraints=True, combined_z=True, irrev_geq=False):
        # targets is a list of (T,t) pairs that represent T <= t
        # combined_z will probably be fixed to True which implies reduce_constraints=True
        self.model = optlang_interface.Model()
        self.optlang_constraint_class = optlang_interface.Constraint
        if bigM <= 0 and self.optlang_constraint_class._INDICATOR_CONSTRAINT_SUPPORT is False:
            raise IndicatorConstraintsNotSupported("This solver does not support indicators. Please choose a differen solver or use a big M formulation.")
        self.optlang_variable_class = optlang_interface.Variable
        irr = [not r for r in reversible]
        self.num_reac = len(rev)
        if cuts is None:
            cuts = [True] * self.num_reac #[True for i in range(self.num_reac)]
            irrepressible = []
        else:
            pass
            #cuts= logical(cuts(:)'); %A make row vector
            #irrepressible= find(~cuts);
            #iv_cost(irrepressible)= 0;
        num_targets = len(targets)
        use_kn_in_dual = kn is not None
        if split_reversible_v:
            split_v_idx = [i for i, x in enumerate(reversible) if x]
            dual_rev_neg_idx = [i for i in range(self.num_reac, self.num_reac + len(split_v_idx))]
            dual_rev_neg_idx_map = [None] * self.num_reac
            for i in range(len(split_v_idx)):
                dual_rev_neg_idx_map[split_v_idx[i]]= dual_rev_neg_idx[i];
            #print(split_v_idx)
            #print(dual_rev_neg_idx)
            #print(dual_rev_neg_idx_map)
        else:
            split_v_idx = []

        self.zero_objective= optlang_interface.Objective(0, direction='min', name='zero_objective')
        self.model.objective= self.zero_objective;
        self.z_vars = [self.optlang_variable_class("Z"+str(i), type="binary", problem=self.model.problem) for i in range(self.num_reac)]
        self.model.add(self.z_vars)
        self.minimize_sum_over_z= optlang_interface.Objective(add(self.z_vars), direction='min', name='minimize_sum_over_z')
        if num_targets == 1:
            #obj.z_var_names= cell(obj.num_reac + length(obj.rev_pos_idx), 1);
            #obj.z_var_names(1:obj.num_reac)= strcat(z_string, nums_idx(1:obj.num_reac));
            #obj.z_var_names(obj.rev_neg_idx)= strcat('ZN', nums_idx(obj.rev_pos_idx));
            z_local = [self.z_vars] # global and local Z are the same if there is only one target
            #iv_cost= [iv_cost, iv_cost(obj.rev_pos_idx)];
        else:
            pass
            # z_local= cell(obj.num_reac + length(obj.rev_pos_idx), num_targets);
            # obj.z_var_names= strcat('Z', numsn); % global Z
            # obj.split_z= false;
            # for k= 1:num_targets
            # z_local(1:obj.num_reac, k)= strcat(sprintf('%s%d_', z_string, k), nums_idx(1:obj.num_reac));
            # z_local(obj.rev_neg_idx, k)= strcat(sprintf('ZN%d_', k), nums_idx(obj.rev_pos_idx));
            # end

        dual_vars = [None] * num_targets
        num_dual_cols = [0] * num_targets # noch nötig?
        for k in range(num_targets):
            # !! unboundedness is only properly represented by None with optlang; using inifinity may cause trouble !!
            dual_lb = [None] * self.num_reac # optlang interprets None as Inf
            #dual_lb = numpy.full(self.num_reac, numpy.NINF)
            dual_ub = [None] * self.num_reac
            #dual_ub = numpy.full(self.num_reac, numpy.inf) # can lead to GLPK crash when trying to otimize an infeasible MILP
            # GLPK treats infinity different than declaring unboundedness explicitly by glp_set_col_bnds ?!?
            # could use numpy arrays and convert them to lists where None replaces inf before calling optlang
            if split_reversible_v:
                    for i in range(self.num_reac):
                        if irrev_geq or reversible[i]:
                            dual_lb[i] = 0
            else:
                if irrev_geq:
                    for i in range(self.num_reac):
                        dual_lb[i] = 0
                for i in irrepressible:
                    if reversible[i]:
                        dual_lb[i] = 0
            for i in irrepressible:
                dual_ub[i] = 0
            if split_reversible_v:
                dual_vars[k] = [self.optlang_variable_class("DP"+str(k)+"_"+str(i), lb=dual_lb[i], ub=dual_ub[i]) for i in range(self.num_reac)] + \
                    [self.optlang_variable_class("DN"+str(k)+"_"+str(i), ub=0) for i in split_v_idx]
                for i in irrepressible:
                    if reversible[i]:
                         dual_vars[k][i].lb = 0
            else:
                dual_vars[k] = [self.optlang_variable_class("DR"+str(k)+"_"+str(i)) for i in range(self.num_reac)]
            first_w= len(dual_vars[k]) # + 1;
            if use_kn_in_dual is False:
                dual = numpy.eye(self.num_reac)
                if split_reversible_v:
                    dual = numpy.hstack((dual, dual[:, split_v_idx]))
                #st_T_part = numpy.hstack((st.transpose(), targets[k][0].transpose()))
                #dual = numpy.hstack((dual, st_T_part))
                dual = numpy.hstack((dual, st.transpose(), targets[k][0].transpose()))
                #print(dual)
                dual_vars[k] += [self.optlang_variable_class("DS"+str(k)+"_"+str(i)) for i in range(st.shape[0])]
                first_w += st.shape[0]
            else:
                pass
    #       switch split_level
    #         case 1 % split dual vars associated with reversible reactions
    #           dual= [kn', kn(~irr, :)', kn'*T{k}'];
    #         case 2 % split all dual vars which are associated with reactions into DN <= 0, DP >= 0
    #           dual= [kn', kn', kn'*T{k}'];
    #         otherwise % no splitting
    #           dual= [kn', kn'*T{k}'];
    #       end
            dual_vars[k] += [self.optlang_variable_class("DT"+str(k)+"_"+str(i), lb=0) for i in range(targets[k][0].shape[0])]
            self.model.add(dual_vars[k])
            num_dual_cols[k]= dual.shape[1]
            constr= [None] * (dual.shape[0]+1)
            print(dual_vars[k][first_w:])
            for i in range(dual.shape[0]):
                if irrev_geq and irr[i]:
                    ub = None
                else:
                    ub = 0
                expr = add([cf * var for cf, var in zip(dual[i, :], dual_vars[k]) if cf != 0])
                #print(expr)
                constr[i] = self.optlang_constraint_class(expr, lb=0, ub=ub, name="D"+str(k)+"_"+str(i), sloppy=True)
                #print(constr[i])
            expr = add([cf * var for cf, var in zip(targets[k][1], dual_vars[k][first_w:]) if cf != 0])
            constr[-1] = self.optlang_constraint_class(expr, ub=-threshold, name="DW"+str(k), sloppy=True)
            self.model.add(constr)

            # constraints for the target(s) (cuts and knock-ins)
            if bigM > 0:
                for i in range(self.num_reac):
                    if cuts[i]:
                        self.model.add(self.optlang_constraint_class(dual_vars[k][i] - bigM*z_local[k][i],
                                       ub=0, name=z_local[k][i].name+dual_vars[k][i].name))
                        if reversible[i]:
                            if split_reversible_v:
                                dn = dual_vars[k][dual_rev_neg_idx_map[i]]
                            else:
                                dn = dual_vars[k][i]
                            self.model.add(self.optlang_constraint_class(dn + bigM*z_local[k][i],
                                           lb=0, name=z_local[k][i].name+dn.name+"r"))

    #         if knock_in(i)
    #           lpfw.write_z_flux_link(obj.z_var_names{i}, dual_var_names{k}{i}, bigM, '<=');
    #           if ~irr(i)
    #             switch split_level
    #               case 1
    #                 dn= dual_var_names{k}{dual_rev_neg_idx_map(i)};
    #               case 2
    #                 dn= dual_var_names{k}{obj.num_reac+i};
    #               otherwise
    #                 dn= dual_var_names{k}{i};
    #             end
    #             lpfw.write_z_flux_link(obj.z_var_names{i}, dn, -bigM, '>=');
    #           end
    #         end
    #       end
            else: # indicators
                for i in range(self.num_reac):
                    if cuts[i]:
                        if split_reversible_v:
                            self.model.add(self.optlang_constraint_class(dual_vars[k][i], ub=0,
                                           indicator_variable=z_local[k][i], active_when=0,
                                           name=z_local[k][i].name+dual_vars[k][i].name))
                            if reversible[i]:
                                dn = dual_vars[k][dual_rev_neg_idx_map[i]]
                                self.model.add(self.optlang_constraint_class(dn, lb=0,
                                               indicator_variable=z_local[k][i], active_when=0,
                                               name=z_local[k][i].name+dn.name))
                        else:
                            if irr[i]:
                                lb = None
                            else:
                                lb = 0
                            self.model.add(self.optlang_constraint_class(dual_vars[k][i], lb=lb, ub=0,
                                           indicator_variable=z_local[k][i], active_when=0,
                                           name=z_local[k][i].name+dual_vars[k][i].name))

    #         if knock_in(i)
    #           fprintf(lpfw_fid, '%s = 1 -> %s <= 0\n', obj.z_var_names{i}, dual_var_names{k}{i});
    #           if ~irr(i)
    #             switch split_level
    #               case 1
    #                 dn= dual_var_names{k}{dual_rev_neg_idx_map(i)};
    #               case 2
    #                 dn= dual_var_names{k}{obj.num_reac+i};
    #               otherwise
    #                 dn= dual_var_names{k}{i};
    #             end
    #             fprintf(lpfw_fid, '%s = 1 -> %s >= 0\n', obj.z_var_names{i}, dn);
    #           end
    #         end
    #       end
    #     end % if bigM > 0
    #   end % for k= 1:num_targets
    
        print(dual_vars)

    def single_solve(self):
        self.model.optimize()
        #try: # some solvers throw exception when trying to query a non-existing result
        if self.model.status is "optimal" or self.model.status is "feasible": # hopefully safe
            print(self.model.objective.value)
            coeff= tuple(round(zv.primal) for zv in self.z_vars)
            #coeff= [round(zv.primal) for zv in self.z_vars]
            #coeff = numpy.zeros(len(self.z_vars), dtype=float64) # klappt noch nicht
            #for i in range(len(self.z_vars)):
            #    coeff[i] = round(self.z_vars[i])
            return coeff
        #except:
        else:
            return None

    def add_exclusion_constraint(self, mcs):
        #expression = sum([cf * var for cf, var in zip(mcs, self.z_vars) if cf != 0])
        expression = add([cf * var for cf, var in zip(mcs, self.z_vars) if cf != 0]) # mul instead of * does not work directly
        ub = sum(mcs)-1;
        self.model.add(self.optlang_constraint_class(expression, ub=ub, sloppy=True))

    def enumerate_mcs(self):
        all_mcs= [];
        while True:
            mcs = self.single_solve()
            if self.model.status == 'optimal':
                self.add_exclusion_constraint(mcs)
                all_mcs.append(mcs)
                if len(all_mcs) == 84:
                    print("HERE")
                # can also increase lower bound of evs_sz constraint
            else:
                break
        print(self.model.status)
        return all_mcs

def equations_to_matrix(model, equations):
    # add option to use names instead of ids
    # allow equations to be a list of lists
    dual = cobra.Model()
    reaction_ids = [r.id for r in model.reactions]
    dual.add_metabolites([cobra.Metabolite(r) for r in reaction_ids])
    for i in range(len(equations)):
        r = cobra.Reaction("R"+str(i)) 
        dual.add_reaction(r)
        r.build_reaction_from_string('=> '+equations[i])
    dual = cobra.util.array.create_stoichiometric_matrix(dual, array_type='DataFrame')
    if numpy.all(dual.index.values == reaction_ids):
        return dual.values.transpose()
    else:
        raise RuntimeError("Index order was not preserved.")

"""
m = cobra.io.read_sbml_model(r"../projects/SmallExample2/SmallExample2.xml")
#[rxn.id for rxn in m.reactions]
#st = cobra.util.array.create_stoichiometric_matrix(m)
stdf = cobra.util.array.create_stoichiometric_matrix(m, array_type='DataFrame')
rev = [r.reversibility for r in m.reactions]
# target = [(numpy.zeros((1,10)), [-1])]
# target[0][0][0, stdf.columns.get_loc('R4')] = -1 # R4 >= 1
target = [(-equations_to_matrix(m, ["R4"]), [-1])]
#print(stdf.columns[3])
#e = ConstrainedMinimalCutSetsEnumerator(optlang.cplex_interface, st, rev, target, split_reversible_v=True)
e = ConstrainedMinimalCutSetsEnumerator(optlang.cplex_interface, stdf.values, rev, target, split_reversible_v=True)
#e.model.optimize() 
#e.model.problem.write('test.lp')
e.model.objective= e.minimize_sum_over_z
mcs1 = e.enumerate_mcs()
"""

#import os
#print(os.getcwd())
ex = cobra.io.read_sbml_model(r"/scratch/vonkamp/gwdg_owncloud/CNApy/metatool_example_no_ext.xml")
stdf = cobra.util.array.create_stoichiometric_matrix(ex, array_type='DataFrame')
rev = [r.reversibility for r in ex.reactions]
#target = [(-equations_to_matrix(ex, ["Pyk", "Pck"]), [-1, -1])]
target = [(equations_to_matrix(ex, ["-1 Pyk", "-1 Pck"]), [-1, -1])] # -Pyk does not work
e = ConstrainedMinimalCutSetsEnumerator(optlang.cplex_interface, stdf.values, rev, target,
                                        split_reversible_v=True, irrev_geq=True)
e.model.objective = e.minimize_sum_over_z
e.model.optimize() 
e.model.problem.write('testI.lp')
mcs = e.enumerate_mcs()

e = ConstrainedMinimalCutSetsEnumerator(optlang.glpk_interface, stdf.values, rev, target, 
                                        bigM= 100, threshold=0.1, split_reversible_v=True, irrev_geq=True)
e.model.objective = e.minimize_sum_over_z
e.model.optimize() 
glp_write_lp(e.model.problem, None, 'testM.lp')
mcs2 = e.enumerate_mcs()

print(len(set(mcs).intersection(set(mcs2))))
print(set(mcs) == set(mcs2))

#import sympy

#def kernel(A):
#    rA = sympy.Matrix.zeros(A.shape[0], A.shape[1])
#    idx= A.nonzero()
#    for i in range(len(idx[0])):
#        rA[idx[0][i], idx[1][i]] = sympy.Rational(A[idx[0][i], idx[1][i]])
#    rA = rA.rref()
#    return rA

#a=kernel(st*numpy.pi)
#t = time.time(); a=kernel(numpy.random.random((10,30))); elapsed = time.time() - t