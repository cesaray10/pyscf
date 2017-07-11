;;;;
;;;; Copyright (C) 2015-  Qiming Sun <osirpt.sun@gmail.com>
;;;; Description:
;;;;

(load "utility.cl")
(load "parser.cl")
(load "derivator.cl")

(defun gen-subscript (cells-streamer raw-script)
  (labels ((gen-tex-iter (raw-script)
             (cond ((null raw-script) raw-script)
                   ((vector? raw-script)
                    (gen-tex-iter (comp-x raw-script))
                    (gen-tex-iter (comp-y raw-script))
                    (gen-tex-iter (comp-z raw-script)))
                   ((cells? raw-script)
                    (funcall cells-streamer raw-script))
                   (t (mapcar cells-streamer raw-script)))))
    (gen-tex-iter raw-script)))

(defun convert-from-n-sys (ls n)
  (reduce (lambda (x y) (+ (* x n) y)) ls
          :initial-value 0))

(defun xyz-to-ternary (xyzs)
  (cond ((eql xyzs 'x) 0)
        ((eql xyzs 'y) 1)
        ((eql xyzs 'z) 2)
        (t (error " unknown subscript ~a" xyzs))))

(defun ternary-subscript (ops)
  "convert the polynomial xyz to the ternary"
  (cond ((null ops) ops)
        (t (convert-from-n-sys (mapcar #'xyz-to-ternary 
                                       (remove-if (lambda (x) (eql x 's))
                                                  (scripts-of ops)))
                               3))))
(defun gen-c-block (fout fmt-gout raw-script)
  (let ((ginc -1))
    (labels ((c-filter (cell)
               (let ((fac (realpart (phase-of cell)))
                     (const@3 (ternary-subscript (consts-of cell)))
                     (op@3    (ternary-subscript (ops-of cell))))
                 (if (equal fac 1)
                   (cond ((null const@3)
                          (if (null op@3)
                            (format fout " + s\[0\]" )
                            (format fout " + s\[~a\]" op@3)))
                         ((null op@3)
                          (format fout " + c\[~a\]*s\[0\]" const@3))
                         (t (format fout " + c\[~a\]*s\[~a\]" const@3 op@3)))
                   (cond ((null const@3)
                          (if (null op@3)
                            (format fout " + (~a*s\[0\])" fac)
                            (format fout " + (~a*s\[~a\])"
                                    fac op@3)))
                         ((null op@3)
                          (format fout " + (~a*c\[~a\]*s\[0\])"
                                  fac const@3))
                         (t (format fout " + (~a*c\[~a\]*s\[~a\])"
                                    fac const@3 op@3))))))
             (c-streamer (cs)
               (format fout fmt-gout (incf ginc))
               (cond ((null cs) (format fout " 0"))
                     ((cell? cs) (c-filter cs))
                     (t (mapcar #'c-filter cs)))
               (format fout ";~%")))
      (gen-subscript #'c-streamer raw-script)
      (1+ ginc))))
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;

;;; effective keys are p,r,ri,...
(defun effect-keys (ops)
  (remove-if-not (lambda (x) (member x *intvar*))
                 ops))
(defun g?e-of (key)
  (case key
    ((p ip nabla px py pz) "D_")
    ((r x y z ri xi yi zi) "R_") ; the vector origin is on the center of the basis it acts on
    ((r0 x0 y0 z0 g) "R0") ; R0 ~ the vector origin is (0,0,0)
    ((rc xc yc zc) "RC") ; the vector origin is set in env[PTR_COMMON_ORIG]
    ((nabla-rinv nabla-r12 breit-r1 breit-r2) "D_")
    (otherwise (error "unknown key ~a~%" key))))

(defun dump-header (fout)
  (format fout "/*
 * Copyright (C) 2016-  Qiming Sun <osirpt.sun@gmail.com>
 * Description: code generated by  gen-code.cl
 */
#include \"grid_ao_drv.h\"
#include \"vhf/fblas.h\"
"))

(defun dump-declare-dri-for-rc (fout i-ops symb)
  (when (intersection '(rc xc yc zc) i-ops)
    (format fout "double dr~a[3];~%" symb)
    (format fout "dr~a[0] = r~a[0] - env[PTR_COMMON_ORIG+0];~%" symb symb)
    (format fout "dr~a[1] = r~a[1] - env[PTR_COMMON_ORIG+1];~%" symb symb)
    (format fout "dr~a[2] = r~a[2] - env[PTR_COMMON_ORIG+2];~%" symb symb))
  (when (intersection '(ri xi yi zi) i-ops)
    (if (intersection '(rc xc yc zc) i-ops)
      (error "Cannot declare dri because rc and ri coexist"))
    (format fout "double dr~a[3];~%" symb)
    (format fout "dr~a[0] = r~a[0] - ri[0];~%" symb symb)
    (format fout "dr~a[1] = r~a[1] - ri[1];~%" symb symb)
    (format fout "dr~a[2] = r~a[2] - ri[2];~%" symb symb)))

(defun dump-declare-giao (fout expr)
  (let ((n-giao (count 'g expr)))
    (when (> n-giao 0)
      (format fout "double c[~a];~%" (expt 3 n-giao))
      (loop
        for i upto (1- (expt 3 n-giao)) do
        (format fout "c[~a] = 1" i)
        (loop
          for j from (1- n-giao) downto 0
          and res = i then (multiple-value-bind (int res) (floor res (expt 3 j))
                             (format fout " * (-ri[~a])" int)
                             res))
        (format fout ";~%")))))

(defun last-bit1 (n)
  ; how many 0s follow the last bit 1
  (loop
    for i upto 31
    thereis (if (oddp (ash n (- i))) i)))
(defun combo-op (fout fmt-op op-rev ig)
  (let* ((right (last-bit1 ig))
         (ig0 (- ig (ash 1 right)))
         (op (nth right op-rev)))
    (format fout fmt-op (g?e-of op) ig ig0 right)))

(defun power2-range (n &optional (shift 0))
  (range (+ shift (ash 1 n)) (+ shift (ash 1 (1+ n)))))
(defun dump-combo-op (fout fmt-op op-rev)
  (let ((op-len (length op-rev)))
    (loop
      for right from 0 to (1- op-len) do
      (loop
        for ig in (power2-range right) do
        (combo-op fout fmt-op op-rev ig)))))

(defun dec-to-ybin (n)
  (parse-integer (substitute #\0 #\2 (write-to-string n :base 3))
                 :radix 2))
(defun dec-to-zbin (n)
  (parse-integer (substitute #\1 #\2
                             (substitute #\0 #\1
                                         (write-to-string n :base 3)))
                 :radix 2))
(defun dump-s-1e (fout n)
  (loop
    for i upto (1- (expt 3 n)) do
    (let* ((ybin (dec-to-ybin i))
           (zbin (dec-to-zbin i))
           (xbin (- (ash 1 n) 1 ybin zbin)))
      (format fout "s[~a] = exps[i] * fx~a[lx] * fy~a[ly] * fz~a[lz];~%"
              i xbin ybin zbin))))

;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;

(defun gen-code-eval-ao (fout intname expr &optional (sp 'spinor))
  (let* ((op-rev (reverse (effect-keys expr)))
         (op-len (length op-rev))
         (raw-script (eval-gto expr))
         (ts1 (car raw-script))
         (sf1 (cadr raw-script))
         (strout (make-string-output-stream))
         (goutinc (gen-c-block strout "gto~d[n*blksize+i] =" (last1 raw-script)))
         (e1comps (if (eql sf1 'sf) 1 4))
         (tensors (/ goutinc e1comps)))
    (format fout "/*  ~{~a ~}|GTO> */~%" expr)
    (format fout "static void shell_eval_~a(double *cgto, double *ri, double *exps,
double *coord, double *alpha, double *coeff,
int l, int np, int nc, int blksize)
{" intname)
    (format fout "
const int degen = (l+1)*(l+2)/2;
const int mblksize = blksize * degen;
const int gtosize = np * mblksize;
int lx, ly, lz, i, k, n;
double fx0[16*~d];
double fy0[16*~d];
double fz0[16*~d];~%" (ash 1 op-len) (ash 1 op-len) (ash 1 op-len))
    (loop
       for i in (range (1- (ash 1 op-len))) do
         (format fout "double *fx~d = fx~d + 16;~%" (1+ i) i)
         (format fout "double *fy~d = fy~d + 16;~%" (1+ i) i)
         (format fout "double *fz~d = fz~d + 16;~%" (1+ i) i))
    (format fout "double gtobuf[gtosize*~d];~%" goutinc)
    (format fout "double *gto0 = gtobuf;~%")
    (loop
       for i in (range (1- goutinc)) do
         (format fout "double *gto~d = gto~d + gtosize;~%" (1+ i) i))
    (format fout "double *gridx = coord;
double *gridy = coord+blksize;
double *gridz = coord+blksize*2;
double s[~d];~%" (expt 3 op-len))
    (dump-declare-dri-for-rc fout expr "i")
    (dump-declare-giao fout expr)
    (format fout "for (k = 0; k < np; k++) {
                 for (i = 0; i < blksize; i++) {
                         if (NOTZERO(exps[i])) {
fx0[0] = 1;
fy0[0] = 1;
fz0[0] = 1;
for (lx = 1; lx <= l+~d; lx++) {
        fx0[lx] = fx0[lx-1] * gridx[i];
        fy0[lx] = fy0[lx-1] * gridy[i];
        fz0[lx] = fz0[lx-1] * gridz[i];
}~%" op-len)
;;; generate g_(bin)
    (dump-combo-op fout "GTO_~aI(~d, ~d, l+~a);~%" op-rev)
;;; dump result of eval-int
    (format fout "for (lx = l, n = 0; lx >= 0; lx--) {
         for (ly = l - lx; ly >= 0; ly--, n++) {
                 lz = l - lx - ly;~%")
    (dump-s-1e fout op-len)
    (format fout "~a        } }
                         } else {
for (n = 0; n < degen; n++) {~%" (get-output-stream-string strout))
    (loop
       for i in (range goutinc) do
         (format fout "gto~d[n*blksize+i] = 0;~%" i))
    (format fout "} } }
exps += blksize;~%")
    (loop
       for i in (range goutinc) do
         (format fout "gto~d += mblksize;~%" i))
    (format fout "}
const char TRANS_N = 'N';
const double D0 = 0;
const double D1 = 1;
for (k = 0; k < ~d; k++) {
        dgemm_(&TRANS_N, &TRANS_N, &mblksize, &nc, &np,
               &D1, gtobuf+gtosize*k, &mblksize, coeff, &np,
               &D0, cgto+nc*mblksize*k, &mblksize);
} }~%" goutinc)

;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;;; determine function caller
    (format fout "static int fexp_~a(double *eprim, double *coord, double *alpha, double *coeff,
int l, int nprim, int nctr, int blksize, double fac)
{
return GTOprim_exp(eprim, coord, alpha, coeff, l, nprim, nctr, blksize, fac*~a);
}~%" intname (factor-of expr))
    (format fout "void ~a(int nao, int ngrids,int blksize, int bastart, int bascount,
double *ao, double *coord, char *non0table,
int *atm, int natm, int *bas, int nbas, double *env)
{~%" intname)
    (format fout "int param[] = {~d, ~d};~%" e1comps tensors)
    (cond ((eql sp 'spinor)
           (format fout "GTOeval_spinor_drv(shell_eval_~a, fexp_~a, GTOc2s_~a~a,
param, nao, ngrids,blksize, bastart, bascount,ao, coord, non0table,
atm, natm, bas, nbas, env);~%}~%" intname intname
                   (if (eql sf1 'sf) "sf" "si")
                   (if (eql ts1 'ts) "" "_i")))
          ((eql sp 'spheric)
           (format fout "GTOeval_sph_drv(shell_eval_~a, fexp_~a,
param, nao, ngrids,blksize, bastart, bascount,ao, coord, non0table,
atm, natm, bas, nbas, env);~%}~%" intname intname))
          ((eql sp 'cart)
           (format fout "GTOeval_cart_drv(shell_eval_~a, fexp_~a,
param, nao, ngrids,blksize, bastart, bascount,ao, coord, non0table,
atm, natm, bas, nbas, env);~%}~%" intname intname)))))
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;

(defun gen-eval (filename &rest items)
  "sp can be one of 'spinor 'spheric 'cart"
  (with-open-file (fout (mkstr filename)
                        :direction :output :if-exists :supersede)
    (dump-header fout)
    (flet ((gen-code (item)
             (let ((intname (mkstr (car item)))
                   (sp (cadr item))
                   (raw-infix (caddr item)))
               (if (member sp '(spinor spheric cart))
                   (gen-code-eval-ao fout intname raw-infix sp)
                   (error "gen-cint: unknown ~a in ~a~%" sp item)))))
      (mapcar #'gen-code items))))

;; vim: ft=lisp