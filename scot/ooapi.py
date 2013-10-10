# Released under The MIT License (MIT)
# http://opensource.org/licenses/MIT
# Copyright (c) 2013 SCoT Development Team

""" Object oriented API to SCoT """

import numpy as np
from .varica import mvarica
from .datatools import dot_special
from .connectivity import Connectivity
from . import var
from eegtopo.topoplot import Topoplot

try:
    import matplotlib.pyplot as plt
    _have_pyplot = True
except ImportError:
    _have_pyplot = False

class SCoT:
    
    def __init__(self, var_order, var_delta=None, locations=None, reducedim=0.99, nfft=512, backend=None):
        self.data_ = None
        self.cl_ = None
        self.unmixing_ = None
        self.mixing_ = None
        self.activations_ = None
        self.var_model_ = None
        self.var_cov_ = None
        self.var_order_ = var_order
        self.var_delta_ = var_delta
        self.connectivity_ = None
        self.locations_ = locations
        self.reducedim_ = reducedim
        self.nfft_ = nfft
        self.backend_ = backend
        
        self.topo_ = None
        self.mixmaps_ = []
        self.unmixmaps_ = []
    
    def setData(self, data, cl=None):
        self.data_ = np.atleast_3d(data)
        self.cl_ = cl
        self.var_model_ = None
        self.var_cov_ = None
        self.connectivity_ = None
        
        if self.unmixing_ != None:
            self.activations_ = dot_special(self.data_, self.unmixing_)
    
    def doMVARICA(self):
        if self.data_ == None:
            raise RuntimeError("MVARICA requires data to be set")
        if self.reducedim_ < 1:
            rv = self.reducedim_
            nc = None
        else:
            rv = None
            nc = self.reducedim_
        result = mvarica(X=self.data_, P=self.var_order_, retain_variance=rv, numcomp=nc, delta=self.var_delta_, backend=self.backend_)
        self.mixing_ = result.mixing
        self.unmixing_ = result.unmixing
        self.var_model_ = result.B
        self.var_cov_ = result.C
        self.var_delta_ = result.delta
        self.connectivity_ = Connectivity(self.var_model_, self.var_cov_, self.nfft_)
    
    def fitVAR(self):
        if self.activations_ == None:
            raise RuntimeError("VAR fitting requires activations (call setData after doMVARICA)")
        if self.cl_ == None:
            self.var_model_, self.var_cov_ = var.fit(data=self.activations_, P=self.var_order_, delta=self.var_delta_, return_covariance=True)
            self.connectivity_ = Connectivity(self.var_model_, self.var_cov_, self.nfft_)
        else:
            self.var_model_, self.var_cov_ = var.fit_multiclass(data=self.activations_, cl=self.cl_, P=self.var_order_, delta=self.var_delta_, return_covariance=True)
            self.connectivity_ = {}
            for c in np.unique(self.cl_):
                self.connectivity_[c] = Connectivity(self.var_model_[c], self.var_cov_[c], self.nfft_)
    
    def getConnectivity(self, measure):
        if self.connectivity_ == None:
            raise RuntimeError("Connectivity requires a VAR model (run doMVARICA or fitVAR first)")
        if isinstance(self.connectivity_, dict):
            result = {}
            for c in np.unique(self.cl_):
                result[c] = getattr(self.connectivity_[c], measure)()
            return result
        else:
            return getattr(self.connectivity_, measure)()
    
    def getTFConnectivity(self, measure, winlen, winstep):
        if self.activations_ == None:
            raise RuntimeError("Time/Frequency Connectivity requires activations (call setData after doMVARICA)")
        [N,M,T] = self.activations_.shape
        
        Nstep = (N-winlen)//winstep
        
        if self.cl_ == None:
            result = np.zeros((M, M, Nstep, self.nfft_), np.complex64)
            i = 0
            for n in range(0, N-winlen, winstep):
                win = np.arange(winlen) + n
                data = self.activations_[win,:,:]                
                B, C = var.fit(data, P=self.var_order_, delta=self.var_delta_, return_covariance=True)
                con = Connectivity(B, C, self.nfft_)
                result[:,:,i,:] = getattr(con, measure)()
                i += 1
        
        else:
            result = {}
            for c in np.unique(self.cl_):
                result[c] = np.zeros((M, M, Nstep, self.nfft_), np.complex64)
            i = 0
            for n in range(0, N-winlen, winstep):
                win = np.arange(winlen) + n
                data = self.activations_[win,:,:]                
                B, C = var.fit_multiclass(data, cl=self.cl_, P=self.var_order_, delta=self.var_delta_, return_covariance=True)
                for c in np.unique(self.cl_):
                    con = Connectivity(B[c], C[c], self.nfft_)
                    result[c][:,:,i,:] = getattr(con, measure)()
                i += 1
        return result
        
    def preparePlots(self, mixing=False, unmixing=False):
        if self.locations_ == None:
            raise RuntimeError("Need sensor locations for plotting")
            
        if self.topo_ == None:
            self.topo_ = Topoplot( )
            self.topo_.set_locations(self.locations_)
        
        if mixing and not self.mixmaps_:
            for i in range(self.mixing_.shape[0]):
                self.topo_.set_values(self.mixing_[i,:])
                self.topo_.create_map()
                self.mixmaps_.append(self.topo_.get_map())
        
        if unmixing and not self.unmixmaps_:
            for i in range(self.unmixing_.shape[1]):
                self.topo_.set_values(self.unmixing_[:,i])
                self.topo_.create_map()
                self.unmixmaps_.append(self.topo_.get_map())
                
    def showPlots(self):
        plt.show()
    
    def plotComponents(self, global_scale=None):
        """ global_scale:
               None - scales each topo individually
               1-99 - percentile of maximum of all plots
        """
        if not _have_pyplot:
            raise ImportError("matplotlib.pyplot is required for plotting")
        if self.unmixing_ == None and self.mixing_ == None:
            raise RuntimeError("No components available (run doMVARICA first)")
        self.preparePlots(True, True)
        
        M = self.mixing_.shape[0]
        
        if global_scale:        
            tmp = np.asarray(self.unmixmaps_)
            tmp = tmp[np.logical_not(np.isnan(tmp))]     
            umax = np.percentile(np.abs(tmp), global_scale)
            umin = -umax
            
            tmp = np.asarray(self.mixmaps_)
            tmp = tmp[np.logical_not(np.isnan(tmp))]   
            mmax = np.percentile(np.abs(tmp), global_scale)
            mmin = -mmax
        
        axes = []
        for m in range(M):
            axes.append(plt.subplot(2, M, m+1))
            self.topo_.set_map(self.unmixmaps_[m])
            if global_scale:
                h1 = self.topo_.plot_map(crange=[umin,umax])
            else:
                h1 = self.topo_.plot_map()
            self.topo_.plot_locations()
            self.topo_.plot_head()
            
            axes.append(plt.subplot(2, M, M+m+1))
            self.topo_.set_map(self.mixmaps_[m])
            if global_scale:
                h2 = self.topo_.plot_map(crange=[mmin,mmax])
            else:
                h2 = self.topo_.plot_map()
            self.topo_.plot_locations()
            self.topo_.plot_head()
            
        for a in axes:            
            a.set_yticks([])
            a.set_xticks([])
            a.set_frame_on(False)
            
        axes[0].set_ylabel('Unmixing weights')
        axes[1].set_ylabel('Scalp projections')
        
        #plt.colorbar(h1, plt.subplot(2, M+1, M+1))
        #plt.colorbar(h2, plt.subplot(2, M+1, 0))
    
    def plotConnectivity(self, measure):
        if not __have_pyplot:
            raise ImportError("matplotlib.pyplot is required for plotting")