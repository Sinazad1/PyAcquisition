# -*- coding: utf-8 -*-
"""
Modified conductivity analysis library for UI display
Captures plot images for display in the analysis mode UI

Doc status: done, MK, 01/30/2026

"""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from io import BytesIO

def fit_standard_model_conductivity_2_with_plot(d_plateau_fit, sensor_temperature, ref_plateau_fit, 
                                                  sensor_name, step_lbl, pdf_pages):
    """
    Modified version that returns plot image data for UI display
    """
    from scipy.optimize import curve_fit
    
    # Conductivity model
    def conductivity_model_2(Z_T_data, K, alpha, eta, zeta):
        """
        Enhanced conductivity model for UI display.
        
        Local definition of the 4-parameter conductivity model used within
        the UI fitting routine. Identical to the main library version but
        defined locally for the UI module.
        
        Args:
            Z_T_data (tuple): Tuple containing (Z, T) where:
                - Z (ndarray): Impedance values.
                - T (ndarray): Temperature values in °C.
            K (float): Calibration coefficient.
            alpha (float): Temperature compensation coefficient.
            eta (float): Impedance scaling factor.
            zeta (float): Impedance offset term.
            
        Returns:
            ndarray: Predicted conductivity values in mS/cm.
        """
        Z, T = Z_T_data
        return (K/(eta*Z+zeta)) * (1 + alpha*(25-T))
    
    # Your data
    Z_data = d_plateau_fit**-1
    T_data = sensor_temperature
    sigma_data = ref_plateau_fit
    
    # Bounds and initial guess
    initial_guess = [4, 0.02, 1.0, 0.0]
    bounds = ([3, 0.005, 0.5, -1000], [6, 0.04, 3, 1000])
    
    # Fit the model
    popt, pcov = curve_fit(conductivity_model_2, (Z_data, T_data), sigma_data,
                          p0=initial_guess, bounds=bounds, maxfev=5000)
    K_fit, alpha_fit, eta_fit, zeta_fit = popt
    
    # Calculate predictions
    sigma_predicted = conductivity_model_2((Z_data, T_data), K_fit, alpha_fit, eta_fit, zeta_fit)
    
    # Calculate percent errors
    percent_error = (sigma_data - sigma_predicted) / sigma_data * 100
    
    # Statistics
    mean_percent_error = np.mean(percent_error)
    abs_mean_percent_error = np.mean(np.abs(percent_error))
    std_percent_error = np.std(percent_error)
    max_abs_error = np.max(np.abs(percent_error))
    
    # Scatter Plot
    plt.figure(figsize=(8, 6))
    plt.plot(sigma_data, sigma_predicted, 'ko', markerfacecolor='none')
    plt.xlabel('Reference Conductivity')
    plt.ylabel(sensor_name + ' Conductivity')
    plt.title(sensor_name + ' Conductivity Scatter\n' + 
              'Aly Model 2:  $\\hat{C} \\sim \\frac{K}{\\eta R+\\zeta} \\times [1 + \\alpha(25-T)]$')
    pdf_pages.savefig(bbox_inches='tight')
    plt.close()
    
    # BA Plot (Error vs Reference) - This is what we want to capture for UI
    idx_1 = step_lbl == 1
    idx_2 = step_lbl == 2
    
    fig = plt.figure(figsize=(8, 6))
    plt.plot(sigma_data[idx_1], percent_error[idx_1], 'o', color='#d62728', markersize=6, 
             fillstyle='none', markeredgewidth=1.5)
    plt.plot(sigma_data[idx_2], percent_error[idx_2], 'o', color='#1f77b4', markersize=6, 
             fillstyle='none', markeredgewidth=1.5)
    plt.ylim([-8, 8])
    
    # Highlight ±2% range
    plt.axhspan(-2, 2, color='lightblue', alpha=0.7, label='±2% range')
    plt.axhline(y=2, color='gray', linestyle='--', alpha=0.7, label='+2%')
    plt.axhline(y=-2, color='gray', linestyle='--', alpha=0.7, label='-2%')
    
    # Add text label
    x_pos = sigma_data.min() + (sigma_data.max() - sigma_data.min()) * 0.05
    plt.text(x_pos, 2.2, 'Specified Accuracy Range', 
             fontsize=10, 
             bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.9, 
                      edgecolor='#1f77b4', linewidth=1))
    
    plt.title(sensor_name + ' BA Plot, Conductivity Error vs. Conductivity Reference\n' +
              'Aly Model 2:  $\\hat{C} \\sim \\frac{K}{\\eta R+\\zeta} \\times [1 + \\alpha(25-T)]$')
    plt.xlabel('Reference Conductivity')
    plt.ylabel('Percent Error')
    plt.legend(['Experiment 1', 'Experiment 2'])
    
    # Save to PDF
    pdf_pages.savefig(bbox_inches='tight')
    
    # Capture plot as image data for UI
    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=100, bbox_inches='tight')
    buf.seek(0)
    plot_image_data = buf.read()
    buf.close()
    
    plt.close(fig)
    
    return K_fit, alpha_fit, mean_percent_error, abs_mean_percent_error, std_percent_error, max_abs_error, sigma_data, percent_error, eta_fit, zeta_fit, plot_image_data
