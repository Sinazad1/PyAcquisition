# -*- coding: utf-8 -*-
"""
Created on Wed Dec  4 09:56:43 2024

@author: Samir
Updated: 
- Added Dual-Range Aly Model 2 Implementation 
- Worked around sklearn dependencies due to size ballooning with it included
- Optimized for Dual-Range Aly Model 2 
- MK, updated 01/30/2026
"""

# %% Libraries
import numpy  as np
import pandas as pd

# Set matplotlib to non-interactive backend to avoid Qt event loop conflicts
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for PDF generation
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
plt.style.use('bmh')

# Keep scipy.optimize for accurate curve fitting
from scipy.optimize import curve_fit

import os

# %% Helper functions to replace sklearn (but keep scipy.optimize)

def linear_regression(X, y, fit_intercept=True, sample_weight=None):
    """
    Simple linear regression using numpy.
    Replaces sklearn.linear_model.LinearRegression
    
    Parameters:
    X: array-like, shape (n_samples, n_features)
    y: array-like, shape (n_samples,)
    fit_intercept: bool, whether to calculate intercept
    sample_weight: array-like, shape (n_samples,), optional sample weights
    
    Returns:
    coef: coefficients
    intercept: intercept (or 0 if fit_intercept=False)
    """
    X = np.asarray(X)
    y = np.asarray(y)
    
    if X.ndim == 1:
        X = X.reshape(-1, 1)
    
    # Apply sample weights if provided
    if sample_weight is not None:
        sample_weight = np.asarray(sample_weight)
        # Weighted least squares: multiply by sqrt(weights)
        sqrt_w = np.sqrt(sample_weight)
        X_weighted = X * sqrt_w[:, np.newaxis]
        y_weighted = y * sqrt_w
    else:
        X_weighted = X
        y_weighted = y
    
    if fit_intercept:
        # Add column of ones for intercept
        X_with_intercept = np.column_stack([np.ones(len(X_weighted)), X_weighted])
        # Solve using least squares: (X^T X)^-1 X^T y
        params, residuals, rank, s = np.linalg.lstsq(X_with_intercept, y_weighted, rcond=None)
        intercept = params[0]
        coef = params[1:]
    else:
        # No intercept
        params, residuals, rank, s = np.linalg.lstsq(X_weighted, y_weighted, rcond=None)
        intercept = 0.0
        coef = params
    
    return coef, intercept

def predict_linear(X, coef, intercept):
    """
    Make predictions using linear model
    
    Parameters:
    X: array-like, shape (n_samples, n_features)
    coef: coefficients
    intercept: intercept
    
    Returns:
    predictions: array of predicted values
    """
    X = np.asarray(X)
    if X.ndim == 1:
        X = X.reshape(-1, 1)
    return np.dot(X, coef) + intercept

# %% Data Reading Functions
def read_conductivity_data(pwd, data_file, ref_file, event_file, con_impedance_name, temp_impedance_name):
    """
    Read and parse conductivity calibration data from CSV files.
    
    Loads DUT measurements, reference sensor data, and event timestamps from
    separate CSV files. Identifies calibration step indices from event data.
    
    Args:
        pwd (str): Working directory path containing data files.
        data_file (str): Filename for DUT measurement data.
        ref_file (str): Filename for reference sensor data.
        event_file (str): Filename for calibration event timestamps.
        con_impedance_name (str): Column name for conductivity impedance in DUT data.
        temp_impedance_name (str): Column name for temperature impedance in DUT data.
        
    Returns:
        tuple: Contains the following numpy arrays:
            - d_impedance (ndarray): DUT conductivity impedance measurements.
            - pt1000_imp (ndarray): DUT PT1000 temperature impedance measurements.
            - ref_con_1 (ndarray): Reference sensor 1 conductivity values.
            - ref_con_2 (ndarray): Reference sensor 2 conductivity values.
            - ref_temp_1 (ndarray): Reference sensor 1 temperature values.
            - ref_temp_2 (ndarray): Reference sensor 2 temperature values.
            - ref_temp_avg (ndarray): Average of both reference temperatures.
            - step_idx (list): Indices of calibration step transitions.
    """

    dut_data      = pd.read_csv(pwd+data_file, delimiter=',', header = 0) 
    ref_data      = pd.read_csv(pwd+ref_file, delimiter=',', header = None)
    event_data    = pd.read_csv(pwd+event_file, delimiter=',',  header = None).T
    # DUT
    d_impedance  = np.array(dut_data[con_impedance_name])
    pt1000_imp   = np.array(dut_data[temp_impedance_name])

    # Ref
    ref_con_1    = np.array(ref_data[1])
    ref_con_2    = np.array(ref_data[2])
    ref_temp_1   = np.array(ref_data[3])
    ref_temp_2   = np.array(ref_data[4])
    ref_temp_avg = 0.5*(ref_temp_1+ref_temp_2) 


    # Create a copy to avoid chained assignment warning
    dut_data = dut_data.copy()
    dut_data['clean_timestamp'] = pd.to_datetime(dut_data['TIMECODE'].str[:-5])
    step_idx = []
    
    for event in event_data[0]:
        target_time = pd.Timestamp(event[:-5])
        time_diff   = np.abs(dut_data['clean_timestamp']-target_time)
        target_idx  = time_diff.idxmin()
        step_idx.append(target_idx)
        
    step_idx = step_idx[1::2]
    
    return d_impedance, pt1000_imp, ref_con_1, ref_con_2, ref_temp_1, ref_temp_2, ref_temp_avg, step_idx

# %% Plot experiment
def plot_experiment(ref_con_1, ref_con_2, ref_temp_1, ref_temp_2, d_impedance, pt1000_imp, sensor_name, pdf_pages):
    """
    Generate diagnostic plots for conductivity calibration experiment.
    
    Creates and saves four plots showing reference conductivity, reference
    temperature, DUT inverse impedance, and DUT RTD impedance over the
    experimental timeline.
    
    Args:
        ref_con_1 (ndarray): Reference sensor 1 conductivity values.
        ref_con_2 (ndarray): Reference sensor 2 conductivity values.
        ref_temp_1 (ndarray): Reference sensor 1 temperature values.
        ref_temp_2 (ndarray): Reference sensor 2 temperature values.
        d_impedance (ndarray): DUT conductivity impedance measurements.
        pt1000_imp (ndarray): DUT PT1000 temperature impedance measurements.
        sensor_name (str): Name of sensor being calibrated (for plot titles).
        pdf_pages (PdfPages): PDF file object to save plots to.
        
    Returns:
        None: Plots are saved to pdf_pages object.
    """

    # # %% Initial plots
    plt.figure()
    plt.plot(ref_con_1, 'b')
    plt.plot(ref_con_2, 'r')
    plt.xlabel('Sample')
    plt.ylabel('Conductivity [mS/cm]')
    plt.title(sensor_name + ' Sensor Calibration, IBP Reference Conductivity')
    plt.legend(['Reference Conductivity 1', 'Reference Conductivity 2'])
    pdf_pages.savefig(bbox_inches='tight')
    plt.close()

    plt.figure()
    plt.plot(ref_temp_1, 'b')
    plt.plot(ref_temp_2, 'r')
    plt.xlabel('Sample')
    plt.ylabel('Temperature [deg C]')
    plt.title(sensor_name + ' Sensor Calibration, IBP Reference Temperature')
    plt.legend(['Reference Temperature 1', 'Reference Temperature 2'])
    pdf_pages.savefig(bbox_inches='tight')
    plt.close()
    
    plt.figure()
    plt.plot(1/d_impedance, 'b')
    plt.xlabel('Sample')
    plt.ylabel('Inv. Impedance')
    plt.title(sensor_name + ' Conductivity Cal Inverse Impedance')
    plt.ylim([0, 0.008])
    pdf_pages.savefig(bbox_inches='tight')
    plt.close()
    
    plt.figure()
    plt.plot(pt1000_imp, 'b')
    plt.xlabel('Sample')
    plt.ylabel('$Impedance$ $[Ohm]$')
    plt.title(sensor_name + ' RTD Impedance [Ohm]')
    plt.ylim([1080, 1180])
    pdf_pages.savefig(bbox_inches='tight')
    plt.close()
    
    return

# %% Generate fit arrays
def gen_fit_array_from_plateaus(d_impedance, ref_con_1, ref_con_2, pt1000_imp, ref_temp_1, ref_temp_2, step_idx):
    """
    Extract steady-state plateau values for calibration fitting.
    
    Identifies plateau regions in the calibration data based on step indices
    and extracts mean values for conductivity and temperature during each
    calibration step.
    
    Args:
        d_impedance (ndarray): DUT conductivity impedance measurements.
        ref_con_1 (ndarray): Reference sensor 1 conductivity values.
        ref_con_2 (ndarray): Reference sensor 2 conductivity values.
        pt1000_imp (ndarray): DUT PT1000 temperature impedance measurements.
        ref_temp_1 (ndarray): Reference sensor 1 temperature values.
        ref_temp_2 (ndarray): Reference sensor 2 temperature values.
        step_idx (list): Indices marking calibration step transitions.
        
    Returns:
        tuple: Contains arrays of plateau values:
            - d_plateau_fit (ndarray): DUT conductivity plateau values.
            - ref_plateau_fit (ndarray): Average reference conductivity plateau values.
            - temp_fit (ndarray): DUT temperature plateau values.
            - ref_temp_mean_fit (ndarray): Average reference temperature plateau values.
            - ref1_fit (ndarray): Reference 1 conductivity plateau values.
            - ref2_fit (ndarray): Reference 2 conductivity plateau values.
            - temp1_fit (ndarray): Reference 1 temperature plateau values.
            - temp2_fit (ndarray): Reference 2 temperature plateau values.
    """
    
    
    d_plateau_fit       = np.array([])
    ref_plateau_fit     = np.array([])
    temp_fit            = np.array([])
    ref_temp_mean_fit   = np.array([])
    ref1_fit            = np.array([])
    ref2_fit            = np.array([])
    ref_temp1_fit       = np.array([])
    ref_temp2_fit       = np.array([])

    for idx in step_idx:
        
        # Attach
        d_plateau             =     1/d_impedance[idx-5:idx]
        ref_plateau           =     0.5*(ref_con_1[idx-5:idx] + 
                                         ref_con_2[idx-5:idx])
        temperature           =     pt1000_imp[idx-5:idx]
        ref_temp              =     0.5*(ref_temp_1[idx-5:idx]+
                                         ref_temp_2[idx-5:idx])
        ref1_plateau          =     ref_con_1[idx-5:idx]
        ref2_plateau          =     ref_con_2[idx-5:idx]
        ref_temp1_plateau     =     ref_temp_1[idx-5:idx]
        ref_temp2_plateau     =     ref_temp_2[idx-5:idx]
                              
        
        # Save data for fitting
        d_plateau_fit     = np.concatenate((d_plateau_fit, d_plateau))
        ref_plateau_fit   = np.concatenate((ref_plateau_fit, ref_plateau))
        temp_fit          = np.concatenate((temp_fit, temperature))
        ref_temp_mean_fit = np.concatenate((ref_temp_mean_fit, ref_temp))
        ref1_fit          = np.concatenate((ref1_fit, ref1_plateau))
        ref2_fit          = np.concatenate((ref2_fit, ref2_plateau))
        ref_temp1_fit     = np.concatenate((ref_temp1_fit, ref_temp1_plateau))
        ref_temp2_fit     = np.concatenate((ref_temp2_fit, ref_temp2_plateau))
        
    return d_plateau_fit, ref_plateau_fit, temp_fit, ref_temp_mean_fit, ref1_fit, ref2_fit, ref_temp1_fit, ref_temp2_fit
    
# %% Temperature model
def temperature_fit(pt1000_impedance, ref_temp, sensor_name, pdf_pages):
    """
    Fit PT1000 RTD calibration curve to convert impedance to temperature.
    
    Uses linear regression to calibrate the PT1000 resistance temperature
    detector, establishing the relationship between measured impedance and
    actual temperature.
    
    Args:
        pt1000_impedance (ndarray): PT1000 impedance measurements in Ohms.
        ref_temp (ndarray): Corresponding reference temperature values in °C.
        sensor_name (str): Name of sensor being calibrated.
        pdf_pages (PdfPages): PDF file object to save diagnostic plots.
        
    Returns:
        tuple: Contains calibration parameters:
            - model_t: Model object with coef_ and intercept_ attributes
            - temp_percent_error (ndarray): Percent errors for each measurement.
            - temp_mae (float): Mean absolute error.
            - temp_max_err (float): Maximum absolute error.
            - temp_std_err (float): Standard deviation of errors.
    """
    
    # Fit linear model
    X = pt1000_impedance.reshape(-1, 1)
    model_t = type('Model', (), {})()  # Create simple object to mimic sklearn
    model_t.coef_, model_t.intercept_ = linear_regression(X, ref_temp, fit_intercept=True)
    
    # Predict
    temp_predicted = predict_linear(X, model_t.coef_, model_t.intercept_)
    
    # Calculate error statistics
    temp_error = ref_temp - temp_predicted
    temp_percent_error = (temp_error / ref_temp) * 100
    temp_mae = np.mean(np.abs(temp_percent_error))
    temp_max_err = np.max(np.abs(temp_percent_error))
    temp_std_err = np.std(temp_percent_error)

    # Plot
    plt.figure()
    plt.plot(ref_temp, temp_predicted, 'ko', markerfacecolor='none')
    plt.xlabel('Reference Temperature')
    plt.ylabel(sensor_name + ' Temperature')
    plt.title(sensor_name + ' Temperature Scatter')
    pdf_pages.savefig(bbox_inches='tight')
    plt.close()
    
    return model_t, temp_percent_error, temp_mae, temp_max_err, temp_std_err

# %% Conductivity Model 2 (4-parameter Aly Model)

def conductivity_model_2(Z_T_data, K, alpha, eta, zeta):
    """
    Enhanced conductivity model with additional impedance correction parameters.
    
    Implements an extended temperature-compensated conductivity model with
    additional parameters (eta, zeta) to improve fit accuracy across wider
    conductivity ranges.
    
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

# %% Dual-Range Aly Model 2 Implementation
def fit_dual_range_aly_model_2(d_plateau_fit, sensor_temperature, ref_plateau_fit, sensor_name, step_lbl, pdf_pages, constrain_low_range=True):
    """
    Fit three Aly Model 2 models:
    - High range: C > 0.002 S/cm (full 4-parameter model)
    - Low range: C <= 0.002 S/cm (optionally constrained to eta=1, zeta=0)
    - Global: All data combined (full 4-parameter model for prospective discrimination)
    
    Parameters:
    -----------
    d_plateau_fit : array
        Inverse impedance data (1/Z)
    sensor_temperature : array
        Temperature data
    ref_plateau_fit : array
        Reference conductivity data
    sensor_name : str
        Name of sensor for plot titles
    step_lbl : array
        Experiment labels (1 or 2) for coloring plots
    pdf_pages : PdfPages
        PDF file to save plots
    constrain_low_range : bool
        If True, set eta=1 and zeta=0 for low range (reduces to standard model)
        
    Returns:
    --------
    Tuple containing:
        - K_high, alpha_high, eta_high, zeta_high: High range coefficients
        - K_low, alpha_low, eta_low, zeta_low: Low range coefficients
        - K_global, alpha_global, eta_global, zeta_global: Global model coefficients (all data)
        - Statistics for high range: mean_err, abs_mean_err, std_err, max_err
        - Statistics for low range: mean_err_low, abs_mean_err_low, std_err_low, max_err_low
        - Statistics for global model: mean_err_global, abs_mean_err_global, std_err_global, max_err_global
        - Statistics for combined model: mean_err_comb, abs_mean_err_comb, std_err_comb, max_err_comb
        - sigma_data, percent_error, plot_image_data
    """
    
    # Prepare data
    Z_data = d_plateau_fit**-1  # impedance measurements
    T_data = sensor_temperature  # temperatures
    sigma_data = ref_plateau_fit.copy()  # conductivities
    
    # Split data by threshold
    threshold = 0.002  # S/cm
    idx_high = sigma_data > threshold
    idx_low = sigma_data <= threshold
    
    # High range data
    Z_high = Z_data[idx_high]
    T_high = T_data[idx_high]
    sigma_high = sigma_data[idx_high]
    step_lbl_high = step_lbl[idx_high]
    
    # Low range data
    Z_low = Z_data[idx_low]
    T_low = T_data[idx_low]
    sigma_low = sigma_data[idx_low]
    step_lbl_low = step_lbl[idx_low]
    
    # --- FIT HIGH RANGE MODEL (full 4-parameter) ---
    initial_guess_high = [4, 0.02, 1.0, 0.0]
    bounds_high = ([3, 0.005, 0.5, -1000], [6, 0.04, 3, 1000])
    
    popt_high, pcov_high = curve_fit(conductivity_model_2, (Z_high, T_high), sigma_high,
                                     p0=initial_guess_high, bounds=bounds_high, maxfev=5000)
    K_high, alpha_high, eta_high, zeta_high = popt_high
    
    # Predictions and errors for high range
    sigma_pred_high = conductivity_model_2((Z_high, T_high), K_high, alpha_high, eta_high, zeta_high)
    percent_error_high = (sigma_high - sigma_pred_high) / sigma_high * 100
    
    mean_err_high = np.mean(percent_error_high)
    abs_mean_err_high = np.mean(np.abs(percent_error_high))
    std_err_high = np.std(percent_error_high)
    max_err_high = np.max(np.abs(percent_error_high))
    
    # --- FIT LOW RANGE MODEL ---
    if constrain_low_range:
        # Constrained: eta=1, zeta=0 (reduces to standard 2-parameter model)
        def conductivity_model_2_constrained(Z_T_data, K, alpha):
            """
            Constrained version of enhanced conductivity model.
            
            Implements the conductivity model with eta=1 and zeta=0, effectively
            reducing to the standard 2-parameter model. Used for low-range fitting
            where additional parameters may cause overfitting.
            
            Args:
                Z_T_data (tuple): Tuple containing (Z, T) where:
                    - Z (ndarray): Impedance values.
                    - T (ndarray): Temperature values in °C.
                K (float): Calibration coefficient.
                alpha (float): Temperature compensation coefficient.
                
            Returns:
                ndarray: Predicted conductivity values in mS/cm.
            """
            Z, T = Z_T_data
            return (K/Z) * (1 + alpha*(25-T))
        
        initial_guess_low = [4, 0.02]
        bounds_low = ([3, 0.005], [6, 0.04])
        
        popt_low, pcov_low = curve_fit(conductivity_model_2_constrained, (Z_low, T_low), sigma_low,
                                       p0=initial_guess_low, bounds=bounds_low, maxfev=5000)
        K_low, alpha_low = popt_low
        eta_low = 1.0
        zeta_low = 0.0
        
        sigma_pred_low = conductivity_model_2_constrained((Z_low, T_low), K_low, alpha_low)
    else:
        # Unconstrained: full 4-parameter model
        initial_guess_low = [4, 0.02, 1.0, 0.0]
        bounds_low = ([3, 0.005, 0.5, -1000], [6, 0.04, 3, 1000])
        
        popt_low, pcov_low = curve_fit(conductivity_model_2, (Z_low, T_low), sigma_low,
                                       p0=initial_guess_low, bounds=bounds_low, maxfev=5000)
        K_low, alpha_low, eta_low, zeta_low = popt_low
        
        sigma_pred_low = conductivity_model_2((Z_low, T_low), K_low, alpha_low, eta_low, zeta_low)
    
    # Predictions and errors for low range
    percent_error_low = (sigma_low - sigma_pred_low) / sigma_low * 100
    
    mean_err_low = np.mean(percent_error_low)
    abs_mean_err_low = np.mean(np.abs(percent_error_low))
    std_err_low = np.std(percent_error_low)
    max_err_low = np.max(np.abs(percent_error_low))
    
    # --- FIT GLOBAL MODEL (entire dataset) ---
    # Use full 4-parameter model on all data for prospective discrimination
    initial_guess_global = [4, 0.02, 1.0, 0.0]
    bounds_global = ([3, 0.005, 0.5, -1000], [6, 0.04, 3, 1000])
    
    popt_global, pcov_global = curve_fit(conductivity_model_2, (Z_data, T_data), sigma_data,
                                         p0=initial_guess_global, bounds=bounds_global, maxfev=5000)
    K_global, alpha_global, eta_global, zeta_global = popt_global
    
    # Predictions and errors for global model
    sigma_pred_global = conductivity_model_2((Z_data, T_data), K_global, alpha_global, eta_global, zeta_global)
    percent_error_global = (sigma_data - sigma_pred_global) / sigma_data * 100
    
    mean_err_global = np.mean(percent_error_global)
    abs_mean_err_global = np.mean(np.abs(percent_error_global))
    std_err_global = np.std(percent_error_global)
    max_err_global = np.max(np.abs(percent_error_global))
    
    # --- COMBINED PREDICTIONS AND ERRORS ---
    # Reconstruct full predictions array using range-specific models
    sigma_pred_combined = np.zeros_like(sigma_data)
    sigma_pred_combined[idx_high] = sigma_pred_high
    sigma_pred_combined[idx_low] = sigma_pred_low
    
    percent_error_combined = np.zeros_like(sigma_data)
    percent_error_combined[idx_high] = percent_error_high
    percent_error_combined[idx_low] = percent_error_low
    
    # Combined statistics
    mean_err_comb = np.mean(percent_error_combined)
    abs_mean_err_comb = np.mean(np.abs(percent_error_combined))
    std_err_comb = np.std(percent_error_combined)
    max_err_comb = np.max(np.abs(percent_error_combined))
    
    # --- PLOTTING ---
    
    # 1. Scatter plot - High Range
    plt.figure()
    plt.plot(sigma_high, sigma_pred_high, 'ko', markerfacecolor='none', label='High Range')
    plt.xlabel('Reference Conductivity [S/cm]')
    plt.ylabel(sensor_name + ' Conductivity [S/cm]')
    plt.title(sensor_name + ' Conductivity Scatter - High Range (C > 0.002 S/cm)' + 
              '\nAly Model 2:  $\\hat{C} \\sim \\frac{K}{\\eta R+\\zeta} \\times [1 + \\alpha(25-T)]$')
    plt.grid(True, alpha=0.3)
    pdf_pages.savefig(bbox_inches='tight')
    plt.close()
    
    # 2. BA plot - High Range
    idx_1_high = step_lbl_high == 1
    idx_2_high = step_lbl_high == 2
    plt.figure()
    plt.plot(sigma_high[idx_1_high], percent_error_high[idx_1_high], 'o', color='#d62728', 
             markersize=6, fillstyle='none', markeredgewidth=1.5, label='Experiment 1')
    plt.plot(sigma_high[idx_2_high], percent_error_high[idx_2_high], 'o', color='#1f77b4', 
             markersize=6, fillstyle='none', markeredgewidth=1.5, label='Experiment 2')
    plt.ylim([-8, 8])
    plt.axhspan(-2, 2, color='lightblue', alpha=0.7)
    plt.axhline(y=2, color='gray', linestyle='--', alpha=0.7)
    plt.axhline(y=-2, color='gray', linestyle='--', alpha=0.7)
    x_pos = sigma_high.min() + (sigma_high.max() - sigma_high.min()) * 0.05
    plt.text(x_pos, 2.2, 'Specified Accuracy Range', fontsize=10,
             bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.9,
                      edgecolor='#1f77b4', linewidth=1))
    plt.title(sensor_name + ' BA Plot - High Range (C > 0.002 S/cm)\n' +
              'Aly Model 2:  $\\hat{C} \\sim \\frac{K}{\\eta R+\\zeta} \\times [1 + \\alpha(25-T)]$')
    plt.xlabel('Reference Conductivity [S/cm]')
    plt.ylabel('Percent Error [%]')
    plt.legend()
    plt.grid(True, alpha=0.3)
    pdf_pages.savefig(bbox_inches='tight')
    plt.close()
    
    # 3. Scatter plot - Low Range
    plt.figure()
    plt.plot(sigma_low, sigma_pred_low, 'ko', markerfacecolor='none', label='Low Range')
    plt.xlabel('Reference Conductivity [S/cm]')
    plt.ylabel(sensor_name + ' Conductivity [S/cm]')
    if constrain_low_range:
        title_str = (sensor_name + ' Conductivity Scatter - Low Range (C <= 0.002 S/cm)' +
                     '\nAly Model 2 (Constrained eta=1, zeta=0):  $\\hat{C} \\sim \\frac{K}{R} \\times [1 + \\alpha(25-T)]$')
    else:
        title_str = (sensor_name + ' Conductivity Scatter - Low Range (C <= 0.002 S/cm)' +
                     '\nAly Model 2:  $\\hat{C} \\sim \\frac{K}{\\eta R+\\zeta} \\times [1 + \\alpha(25-T)]$')
    plt.title(title_str)
    plt.grid(True, alpha=0.3)
    pdf_pages.savefig(bbox_inches='tight')
    plt.close()
    
    # 4. BA plot - Low Range
    idx_1_low = step_lbl_low == 1
    idx_2_low = step_lbl_low == 2
    plt.figure()
    plt.plot(sigma_low[idx_1_low], percent_error_low[idx_1_low], 'o', color='#d62728',
             markersize=6, fillstyle='none', markeredgewidth=1.5, label='Experiment 1')
    plt.plot(sigma_low[idx_2_low], percent_error_low[idx_2_low], 'o', color='#1f77b4',
             markersize=6, fillstyle='none', markeredgewidth=1.5, label='Experiment 2')
    plt.ylim([-8, 8])
    plt.axhspan(-2, 2, color='lightblue', alpha=0.7)
    plt.axhline(y=2, color='gray', linestyle='--', alpha=0.7)
    plt.axhline(y=-2, color='gray', linestyle='--', alpha=0.7)
    if len(sigma_low) > 0:
        x_pos = sigma_low.min() + (sigma_low.max() - sigma_low.min()) * 0.05
        plt.text(x_pos, 2.2, 'Specified Accuracy Range', fontsize=10,
                 bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.9,
                          edgecolor='#1f77b4', linewidth=1))
    if constrain_low_range:
        title_str = (sensor_name + ' BA Plot - Low Range (C <= 0.002 S/cm)\n' +
                     'Aly Model 2 (Constrained eta=1, zeta=0):  $\\hat{C} \\sim \\frac{K}{R} \\times [1 + \\alpha(25-T)]$')
    else:
        title_str = (sensor_name + ' BA Plot - Low Range (C <= 0.002 S/cm)\n' +
                     'Aly Model 2:  $\\hat{C} \\sim \\frac{K}{\\eta R+\\zeta} \\times [1 + \\alpha(25-T)]$')
    plt.title(title_str)
    plt.xlabel('Reference Conductivity [S/cm]')
    plt.ylabel('Percent Error [%]')
    plt.legend()
    plt.grid(True, alpha=0.3)
    pdf_pages.savefig(bbox_inches='tight')
    plt.close()
    
    # 5. Combined BA plot showing both ranges together
    idx_1 = step_lbl == 1
    idx_2 = step_lbl == 2
    
    fig = plt.figure(figsize=(10, 6))
    
    # Plot high range points
    plt.plot(sigma_data[idx_high & idx_1], percent_error_combined[idx_high & idx_1], 
             'o', color='#d62728', markersize=7, fillstyle='none', markeredgewidth=1.5,
             label='High Range - Exp 1')
    plt.plot(sigma_data[idx_high & idx_2], percent_error_combined[idx_high & idx_2],
             'o', color='#1f77b4', markersize=7, fillstyle='none', markeredgewidth=1.5,
             label='High Range - Exp 2')
    
    # Plot low range points (different marker)
    plt.plot(sigma_data[idx_low & idx_1], percent_error_combined[idx_low & idx_1],
             's', color='#d62728', markersize=7, fillstyle='none', markeredgewidth=1.5,
             label='Low Range - Exp 1')
    plt.plot(sigma_data[idx_low & idx_2], percent_error_combined[idx_low & idx_2],
             's', color='#1f77b4', markersize=7, fillstyle='none', markeredgewidth=1.5,
             label='Low Range - Exp 2')
    
    # Add vertical line at threshold
    plt.axvline(x=threshold, color='black', linestyle=':', linewidth=2, label='Range Boundary')
    
    plt.ylim([-8, 8])
    plt.axhspan(-2, 2, color='lightblue', alpha=0.7)
    plt.axhline(y=2, color='gray', linestyle='--', alpha=0.7)
    plt.axhline(y=-2, color='gray', linestyle='--', alpha=0.7)
    
    x_pos = sigma_data.min() + (sigma_data.max() - sigma_data.min()) * 0.05
    plt.text(x_pos, 2.2, 'Specified Accuracy Range', fontsize=10,
             bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.9,
                      edgecolor='#1f77b4', linewidth=1))
    
    plt.title(sensor_name + ' Combined BA Plot - Dual Range Model\n' +
              'Low Range (<=0.002): ' + ('Constrained Model' if constrain_low_range else 'Full Model') +
              ' | High Range (>0.002): Full Model')
    plt.xlabel('Reference Conductivity [S/cm]')
    plt.ylabel('Percent Error [%]')
    plt.legend(loc='best', fontsize=9)
    plt.grid(True, alpha=0.3)
    pdf_pages.savefig(bbox_inches='tight')
    
    # Capture combined plot as image for UI display
    from io import BytesIO
    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=100, bbox_inches='tight')
    buf.seek(0)
    plot_image_data = buf.read()
    buf.close()
    
    plt.close(fig)
    
    # 6. Global Model Scatter Plot
    plt.figure()
    plt.plot(sigma_data, sigma_pred_global, 'ko', markerfacecolor='none', label='Global Model')
    plt.xlabel('Reference Conductivity [S/cm]')
    plt.ylabel(sensor_name + ' Conductivity [S/cm]')
    plt.title(sensor_name + ' Conductivity Scatter - Global Model (All Data)\n' +
              'Aly Model 2:  $\\hat{C} \\sim \\frac{K}{\\eta R+\\zeta} \\times [1 + \\alpha(25-T)]$')
    plt.grid(True, alpha=0.3)
    pdf_pages.savefig(bbox_inches='tight')
    plt.close()
    
    # 7. Global Model BA Plot
    plt.figure()
    plt.plot(sigma_data[idx_1], percent_error_global[idx_1], 'o', color='#d62728',
             markersize=6, fillstyle='none', markeredgewidth=1.5, label='Experiment 1')
    plt.plot(sigma_data[idx_2], percent_error_global[idx_2], 'o', color='#1f77b4',
             markersize=6, fillstyle='none', markeredgewidth=1.5, label='Experiment 2')
    plt.ylim([-8, 8])
    plt.axhspan(-2, 2, color='lightblue', alpha=0.7)
    plt.axhline(y=2, color='gray', linestyle='--', alpha=0.7)
    plt.axhline(y=-2, color='gray', linestyle='--', alpha=0.7)
    x_pos = sigma_data.min() + (sigma_data.max() - sigma_data.min()) * 0.05
    plt.text(x_pos, 2.2, 'Specified Accuracy Range', fontsize=10,
             bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.9,
                      edgecolor='#1f77b4', linewidth=1))
    plt.title(sensor_name + ' BA Plot - Global Model (All Data)\n' +
              'Aly Model 2:  $\\hat{C} \\sim \\frac{K}{\\eta R+\\zeta} \\times [1 + \\alpha(25-T)]$')
    plt.xlabel('Reference Conductivity [S/cm]')
    plt.ylabel('Percent Error [%]')
    plt.legend()
    plt.grid(True, alpha=0.3)
    pdf_pages.savefig(bbox_inches='tight')
    plt.close()
    
    return (K_high, alpha_high, eta_high, zeta_high,
            K_low, alpha_low, eta_low, zeta_low,
            K_global, alpha_global, eta_global, zeta_global,
            mean_err_high, abs_mean_err_high, std_err_high, max_err_high,
            mean_err_low, abs_mean_err_low, std_err_low, max_err_low,
            mean_err_global, abs_mean_err_global, std_err_global, max_err_global,
            mean_err_comb, abs_mean_err_comb, std_err_comb, max_err_comb,
            sigma_data, percent_error_combined, plot_image_data)
