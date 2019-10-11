import make_test_cell
from pyscf.pbc.tools.pbc import super_cell
from pyscf.pbc import gto
from pyscf.pbc import cc as pbcc
from pyscf.pbc import scf as pbcscf
from pyscf.pbc.cc.eom_kccsd_rhf import EOMIP, EOMEA
from pyscf.pbc.cc.eom_kccsd_rhf import EOMIP_Ta, EOMEA_Ta
from pyscf.cc import eom_uccsd
import unittest

cell_n3d = make_test_cell.test_cell_n3_diffuse()
kmf = pbcscf.KRHF(cell_n3d, cell_n3d.make_kpts((1,1,2), with_gamma_point=True), exxdiv=None)
kmf.conv_tol = 1e-10
kmf.scf()

cell_n3 = make_test_cell.test_cell_n3()
cell_n3.mesh = [29] * 3
cell_n3.build()
kmf_n3 = pbcscf.KRHF(cell_n3, cell_n3.make_kpts([1,1,2]), exxdiv=None)
kmf_n3.kernel()

def tearDownModule():
    global cell_n3d, kmf, cell_n3, kmf_n3
    del cell_n3d, kmf, cell_n3, kmf_n3

class KnownValues(unittest.TestCase):
    def test_n3_diffuse(self):
        nk = (1, 1, 2)
        ehf_bench = -6.1870676561720721
        ecc_bench = -0.06764836939412185

        cc = pbcc.kccsd_rhf.RCCSD(kmf)
        cc.conv_tol = 1e-9
        eris = cc.ao2mo()
        ecc, t1, t2 = cc.kernel(eris=eris)
        ehf = kmf.e_tot
        self.assertAlmostEqual(ehf, ehf_bench, 6)
        self.assertAlmostEqual(ecc, ecc_bench, 6)

        e, v = cc.ipccsd(nroots=2, koopmans=True, kptlist=(0,))
        self.assertAlmostEqual(e[0][0], -1.1489469942237946, 6)
        self.assertAlmostEqual(e[0][1], -1.1088194607458677, 6)
        e, v = cc.eaccsd(nroots=2, koopmans=True, kptlist=(0,))
        self.assertAlmostEqual(e[0][0], 1.2669788600074476, 6)
        self.assertAlmostEqual(e[0][1], 1.278883198038047, 6)

        myeom = EOMIP(cc)
        imds = myeom.make_imds()
        e, v = myeom.ipccsd(nroots=2, koopmans=True, kptlist=(0,), imds=imds)
        self.assertAlmostEqual(e[0][0], -1.1489469942237946, 6)
        self.assertAlmostEqual(e[0][1], -1.1088194607458677, 6)
        e, v = myeom.ipccsd(nroots=2, koopmans=True, kptlist=(1,), imds=imds)
        self.assertAlmostEqual(e[0][0], -0.9074337254867506, 6)
        self.assertAlmostEqual(e[0][1], -0.9074331853695625, 6)
        e, v = myeom.ipccsd(nroots=2, left=True, koopmans=True, kptlist=(0,), imds=imds)
        self.assertAlmostEqual(e[0][0], -1.1489469931063192, 6)
        self.assertAlmostEqual(e[0][1], -1.1088194567671674, 6)
        e, v = myeom.ipccsd(nroots=2, left=True, koopmans=True, kptlist=(1,), imds=imds)
        self.assertAlmostEqual(e[0][0], -0.9074337234999493, 6)
        self.assertAlmostEqual(e[0][1], -0.9074331832202921, 6)

        myeom = EOMEA(cc)
        imds = myeom.make_imds()
        e, v = myeom.eaccsd(nroots=2, koopmans=True, kptlist=(1,))
        self.assertAlmostEqual(e[0][0], 1.2275830143478248, 6)
        self.assertAlmostEqual(e[0][1], 1.3830379248901867, 6)
        e, v = myeom.eaccsd(nroots=2, koopmans=True, kptlist=(0,))
        self.assertAlmostEqual(e[0][0], 1.2669788600074476, 6)
        self.assertAlmostEqual(e[0][1], 1.278883198038047, 6)
        e, v = myeom.eaccsd(nroots=2, left=True, koopmans=True, kptlist=(1,))
        self.assertAlmostEqual(e[0][0], 1.227583012965648, 6)
        self.assertAlmostEqual(e[0][1], 1.383037924670814, 6)
        e, v = myeom.eaccsd(nroots=2, left=True, koopmans=True, kptlist=(0,))
        self.assertAlmostEqual(e[0][0], 1.2669788599162801, 6)
        self.assertAlmostEqual(e[0][1], 1.2788832018377787, 6)

    def test_n3_diffuse_frozen(self):
        nk = (1, 1, 2)
        ehf_bench = -6.1870676561720721
        ecc_bench = -0.0442506265840587

        cc = pbcc.kccsd_rhf.RCCSD(kmf, frozen=[[0],[0,1]])
        cc.conv_tol = 1e-10
        eris = cc.ao2mo()
        ecc, t1, t2 = cc.kernel(eris=eris)
        ehf = kmf.e_tot
        self.assertAlmostEqual(ehf, ehf_bench, 6)
        self.assertAlmostEqual(ecc, ecc_bench, 6)

        e, v = cc.ipccsd(nroots=2, koopmans=True, kptlist=(0,))
        self.assertAlmostEqual(e[0][0], -1.1316152294295743, 6)
        self.assertAlmostEqual(e[0][1], -1.104163717600433, 6)
        e, v = cc.eaccsd(nroots=2, koopmans=True, kptlist=(0,))
        self.assertAlmostEqual(e[0][0], 1.2572812499753756, 6)
        self.assertAlmostEqual(e[0][1], 1.280747357928012, 6)

        e, v = cc.ipccsd(nroots=2, koopmans=True, kptlist=(1,))
        self.assertAlmostEqual(e[0][0], -0.898314514845498, 6)
        self.assertAlmostEqual(e[0][1], -0.8983139526618168, 6)
        e, v = cc.eaccsd(nroots=2, koopmans=True, kptlist=(1,))
        self.assertAlmostEqual(e[0][0], 1.229802633498979, 6)
        self.assertAlmostEqual(e[0][1], 1.384394629885998, 6)

    def test_n3_diffuse_Ta(self):
        nk = (1, 1, 2)
        ehf_bench = -6.1870676561720721
        ecc_bench = -0.06764836939412185

        cc = pbcc.kccsd_rhf.RCCSD(kmf)
        cc.conv_tol = 1e-8
        eris = cc.ao2mo()
        eris.mo_energy = [eris.fock[ikpt].diagonal() for ikpt in range(cc.nkpts)]
        ecc, t1, t2 = cc.kernel(eris=eris)
        ehf = kmf.e_tot
        self.assertAlmostEqual(ehf, ehf_bench, 6)
        self.assertAlmostEqual(ecc, ecc_bench, 6)

        eom = EOMIP_Ta(cc)
        e, v = eom.ipccsd(nroots=2, koopmans=True, kptlist=(0,), eris=eris)
        self.assertAlmostEqual(e[0][0], -1.146351230068405, 6)
        self.assertAlmostEqual(e[0][1], -1.10725570884212, 6)

        eom = EOMEA_Ta(cc)
        e, v = eom.eaccsd(nroots=2, koopmans=True, kptlist=[0], eris=eris)
        self.assertAlmostEqual(e[0][0], 1.267728933294929, 6)
        self.assertAlmostEqual(e[0][1], 1.280954973687476, 6)

        eom = EOMEA_Ta(cc)
        e, v = eom.eaccsd(nroots=2, koopmans=True, kptlist=[1], eris=eris)
        self.assertAlmostEqual(e[0][0], 1.229047959680129, 6)
        self.assertAlmostEqual(e[0][1], 1.384154370672317, 6)

    def test_n3_diffuse_Ta_against_so(self):
        ehf_bench = -6.1870676561720721
        ecc_bench = -0.06764836939412185

        cc = pbcc.kccsd_rhf.RCCSD(kmf)
        cc.conv_tol = 1e-10
        eris = cc.ao2mo()
        eris.mo_energy = [eris.fock[ikpt].diagonal() for ikpt in range(cc.nkpts)]
        ecc, t1, t2 = cc.kernel(eris=eris)
        ehf = kmf.e_tot
        self.assertAlmostEqual(ehf, ehf_bench, 6)
        self.assertAlmostEqual(ecc, ecc_bench, 6)

        eom = EOMEA_Ta(cc)
        eea_rccsd = eom.eaccsd_star(nroots=1, koopmans=True, kptlist=(0,), eris=eris)
        eom = EOMIP_Ta(cc)
        eip_rccsd = eom.ipccsd_star(nroots=1, koopmans=True, kptlist=(0,), eris=eris)
        self.assertAlmostEqual(eea_rccsd[0][0], 1.2610123166324307, 6)
        self.assertAlmostEqual(eip_rccsd[0][0], -1.1435100754903331, 6)

        from pyscf.pbc.cc import kccsd
        cc = pbcc.KGCCSD(kmf)
        cc.conv_tol = 1e-10
        eris = cc.ao2mo()
        eris.mo_energy = [eris.fock[ikpt].diagonal() for ikpt in range(cc.nkpts)]
        ecc, t1, t2 = cc.kernel(eris=eris)
        ehf = kmf.e_tot
        self.assertAlmostEqual(ehf, ehf_bench, 6)
        self.assertAlmostEqual(ecc, ecc_bench, 6)

        from pyscf.pbc.cc import eom_kccsd_ghf
        eom = eom_kccsd_ghf.EOMEA_Ta(cc)
        eea_gccsd = eom.eaccsd_star(nroots=1, koopmans=True, kptlist=(0,), eris=eris)
        eom = eom_kccsd_ghf.EOMIP_Ta(cc)
        eip_gccsd = eom.ipccsd_star(nroots=1, koopmans=True, kptlist=(0,), eris=eris)
        self.assertAlmostEqual(eea_gccsd[0][0], 1.2610123166324307, 6)
        self.assertAlmostEqual(eip_gccsd[0][0], -1.1435100754903331, 6)

        # Usually slightly higher agreement when comparing directly against one another
        self.assertAlmostEqual(eea_gccsd[0][0], eea_rccsd[0][0], 9)
        self.assertAlmostEqual(eip_gccsd[0][0], eip_rccsd[0][0], 9)

    def test_n3_ee(self):
        ehf_bench = -8.65192351414987
        ecc_bench = -0.1552983842036319
        eee_bench = [0.267866987019175  , 0.2678670115360931, 0.2687043844504475]

        ekrhf = kmf_n3.e_tot
        self.assertAlmostEqual(ekrhf, ehf_bench, 6)

        mycc = pbcc.KRCCSD(kmf_n3, keep_exxdiv=True)
        ekrcc, t1, t2 = mycc.kernel()
        self.assertAlmostEqual(ekrcc, ecc_bench, 6)

        # EOM-EE-KRCCSD singlet
        nroots = 3  # number of roots requested
        kptlist = [0]  # index(indices) of targetted k_shift(s) 

        from pyscf.pbc.cc import eom_kccsd_rhf as eom_krccsd
        myeomee = eom_krccsd.EOMEESinglet(mycc)
        myeomee.max_space = nroots * 10
        eee, vee = myeomee.kernel(nroots=nroots, kptlist=kptlist)
        self.assertAlmostEqual(eee[0][0], eee_bench[0], 5)
        self.assertAlmostEqual(eee[0][1], eee_bench[1], 5)
        self.assertAlmostEqual(eee[0][2], eee_bench[2], 5)
        
