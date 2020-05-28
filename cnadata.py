import cobra
from dataclasses import dataclass


class CnaData:
    def __init__(self):
        self.cobra_py_model = cobra.Model()
        self.maps = []
        self.values = {}
        self.modes = []
        # self.modes = [{'ACALD':0.0, 'ACALDt':0.0, 'ACKr':0.0, 'ACONTa':6.007249575350342, 'ACONTb':6.007249575350342, 'ACt2r':0.0, 'ADK1':0.0},
        # {'AKGDH':5.064375661482104, 'AKGt2r':0.0, 'ALCD2x':0.0, 'ATPM':8.39, 'ATPS4r':45.514009774517554},
        # {'BIOMASS_Ecoli_core_w_GAM':0.8739215069684307, 'CO2t':-22.80983331020498, 'CS':6.007249575350342, 'CYTBD':43.598985311997595, 'D_LACt2':0.0, 'ENO':14.716139568742857, 'ETOHt2r':0.0, 'EX_ac_e':0.0, 'EX_acald_e':0.0, 'EX_akg_e':0.0, 'EX_co2_e':22.80983331020498, 'EX_etoh_e':0.0, 'EX_for_e':0.0, 'EX_fru_e':0.0, 'EX_fum_e':0.0, 'EX_glc__D_e':-10.0, 'EX_gln__L_e':0.0},
        # {'EX_glu__L_e':0.0, 'EX_h_e':17.530865429786687, 'EX_h2o_e':29.175827135565815, 'EX_lac__D_e':0.0, 'EX_mal__L_e':0.0, 'EX_nh4_e':-4.76531919319746, 'EX_o2_e':-21.799492655998794, 'EX_pi_e':-3.2148950476847533, 'EX_pyr_e':0.0, 'EX_succ_e':0.0, 'FBA':7.4773819621602975, 'FBP':0.0, 'FORt2':0.0, 'FORt':0.0, 'FRD7':0.0, 'FRUpts2':0.0, 'FUM':5.064375661482102, 'FUMt2_2':0.0, 'G6PDH2r':4.959984944574654, 'GAPD':16.02352614316763},
        # {'GLCpts': 10.0, 'GLNS': 0.22346172933182723, 'GLNabc': 2.722410445957663e-16, 'GLUDy': -4.5418574638656315, 'GLUN': 0.0, 'GLUSy': 0.0, 'GLUt2r': 0.0, 'GND': 4.959984944574654, 'H2Ot': -29.175827135565815, 'ICDHyr': 6.007249575350342, 'ICL': 0.0, 'LDH_D': 0.0, 'MALS': 0.0, 'MALt2_2': 0.0, 'MDH': 5.064375661482103, 'ME1': 0.0, 'ME2': 0.0, 'NADH16': 38.534609650515485, 'NADTRHD': 0.0, 'NH4t': 4.76531919319746},
        # {'O2t':21.799492655998794, 'PDH':9.282532599166627, 'PFK':7.477381962160283, 'PFL':0.0, 'PGI':4.860861146496817, 'PGK':-16.02352614316763, 'PGL':4.959984944574654, 'PGM':-14.716139568742857, 'PIt2r':3.2148950476847533, 'PPC':2.5043094703687347, 'PPCK':0.0, 'PPS':0.0, 'PTAr':0.0, 'PYK':1.7581774441068099, 'PYRt2':0.0, 'RPE':2.6784818505075276, 'RPI':-2.281503094067127, 'SUCCt2_2':0.0, 'SUCCt3':0.0, 'SUCDi':5.064375661482103, 'SUCOAS':-5.064375661482104, 'TALA':1.4969837572615659, 'THD2':0.0, 'TKT1':1.4969837572615665, 'TKT2':1.1814980932459624, 'TPI':7.4773819621602975}]
        self.high = 0.0
        self.low = 0.0

    def set_scen(self, scen):
        self.high = 0.0
        self.low = 0.0
        self.values.clear()
        for key in scen.keys():
            self.values[key] = scen[key]
            if scen[key] > self.high:
                self.high = scen[key]
            if scen[key] < self.low:
                self.low = scen[key]


def CnaMap(name):
    return {"name": name,
            "background": "cnapylogo.svg",
            "bg-size": 1,
            "zoom": 0,
            "pos": (0, 0),
            "boxes": {}
            }
