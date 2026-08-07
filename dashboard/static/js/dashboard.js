/**
 * Water Quality Map Dashboard - JavaScript Logic
 * Handles API calls, UI updates, and map loading
 */

// ==========================================
// State Management
// ==========================================

const DashboardState = {
    maps: [],                    // Array of all map metadata
    parameters: {},              // Grouped maps by parameter
    selectedParameter: null,     // Currently selected parameter
    selectedDateRange: null,   // Currently selected date range
    selectedMap: null,          // Currently displayed map
    viewType: 'district',       // Current view type: 'district' or 'detailed' (default: district)
    isLoading: false            // Loading state flag
};

// Parameter display names and colors
const ParameterInfo = {
    'all_params': {
        displayName: 'All Parameters',
        unit: 'Multi',
        color: '#6f42c1'
    },
    'cl2_free_1': {
        displayName: 'Free Chlorine',
        unit: 'mg/L',
        color: '#0d6efd'
    },
    'ecoli': {
        displayName: 'E. coli',
        unit: 'CFU/100mL',
        color: '#dc3545'
    },
    'turby': {
        displayName: 'Turbidity',
        unit: 'NTU',
        color: '#6c757d'
    }
};

// ==========================================
// Utility Functions
// ==========================================

/**
 * Log message with timestamp
 */
function log(message, type = 'info') {
    const timestamp = new Date().toISOString();
    const prefix = `[${timestamp}] [Dashboard]`;
    
    if (type === 'error') {
        console.error(`${prefix} ERROR:`, message);
    } else if (type === 'warn') {
        console.warn(`${prefix} WARN:`, message);
    } else {
        console.log(`${prefix} INFO:`, message);
    }
}

/**
 * Show loading indicator
 */
function showLoading(message = 'Loading...') {
    DashboardState.isLoading = true;
    const loadingEl = document.getElementById('loading-indicator');
    if (loadingEl) {
        loadingEl.querySelector('p').textContent = message;
        loadingEl.classList.remove('d-none');
    }
}

/**
 * Hide loading indicator
 */
function hideLoading() {
    DashboardState.isLoading = false;
    const loadingEl = document.getElementById('loading-indicator');
    if (loadingEl) {
        loadingEl.classList.add('d-none');
    }
}

/**
 * Show error message
 */
function showError(message) {
    log(message, 'error');
    const errorEl = document.getElementById('error-message');
    const errorText = document.getElementById('error-text');
    if (errorEl && errorText) {
        errorText.textContent = message;
        errorEl.classList.remove('d-none');
    }
}

/**
 * Hide error message
 */
function hideError() {
    const errorEl = document.getElementById('error-message');
    if (errorEl) {
        errorEl.classList.add('d-none');
    }
}

/**
 * Show "no maps" message
 */
function showNoMapsMessage() {
    const noMapsEl = document.getElementById('no-maps-message');
    if (noMapsEl) {
        noMapsEl.classList.remove('d-none');
    }
}

// ==========================================
// API Functions
// ==========================================

/**
 * Fetch maps data from API
 */
async function fetchMaps() {
    log('Fetching maps from API...');
    showLoading('Loading map data...');
    hideError();
    
    try {
        // 修改此处
        const response = await fetch('api/maps');
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.success) {
            throw new Error(data.error || 'API returned unsuccessful response');
        }
        
        log(`Successfully fetched ${data.data.length} maps`);
        return data;
        
    } catch (error) {
        log(`Error fetching maps: ${error.message}`, 'error');
        throw error;
    }
}

// ==========================================
// Data Processing
// ==========================================

/**
 * Process maps data and update state
 */
function processMapsData(data) {
    log('Processing maps data...');
    
    DashboardState.maps = data.data;
    
    // Group maps by parameter
    DashboardState.parameters = {};
    
    DashboardState.maps.forEach(map => {
        const param = map.parameter;
        if (!DashboardState.parameters[param]) {
            DashboardState.parameters[param] = [];
        }
        DashboardState.parameters[param].push(map);
    });
    
    // Sort maps within each parameter group by date (newest first)
    Object.keys(DashboardState.parameters).forEach(param => {
        DashboardState.parameters[param].sort((a, b) => {
            // Sort by date_from descending
            if (a.date_from && b.date_from) {
                const dateCompare = new Date(b.date_from) - new Date(a.date_from);
                if (dateCompare !== 0) return dateCompare;
            }
            // If dates are equal or missing, sort by timestamp
            return (b.timestamp || '').localeCompare(a.timestamp || '');
        });
    });
    
    log(`Processed ${DashboardState.maps.length} maps across ${Object.keys(DashboardState.parameters).length} parameters`);
}

// ==========================================
// UI Population
// ==========================================

/**
 * Populate parameter dropdown
 */
function populateParameterDropdown() {
    log('Populating parameter dropdown...');
    
    const select = document.getElementById('parameter-select');
    if (!select) return;
    
    // Clear existing options except the placeholder
    select.innerHTML = '<option value="" disabled selected>Select parameter...</option>';
    
    // Get unique parameters
    const parameters = Object.keys(DashboardState.parameters).sort();
    
    parameters.forEach(param => {
        const info = ParameterInfo[param] || { displayName: param, unit: '' };
        const option = document.createElement('option');
        option.value = param;
        option.textContent = `${info.displayName}`;
        select.appendChild(option);
    });
    
    log(`Populated dropdown with ${parameters.length} parameters`);
}

/**
 * Populate date range dropdown based on selected parameter
 */
function populateDateRangeDropdown(parameter) {
    log(`Populating date range dropdown for parameter: ${parameter}`);
    
    const select = document.getElementById('date-range-select');
    if (!select) return;
    
    // Clear existing options
    select.innerHTML = '<option value="" disabled selected>Select date range...</option>';
    
    if (!parameter || !DashboardState.parameters[parameter]) {
        select.disabled = true;
        return;
    }
    
    select.disabled = false;
    
    // Get maps for this parameter (already sorted by date)
    const maps = DashboardState.parameters[parameter];
    
    maps.forEach(map => {
        const option = document.createElement('option');
        option.value = map.filename;
        
        // Format display text
        if (map.date_range) {
            option.textContent = map.date_range;
        } else if (map.timestamp) {
            // Format timestamp for display
            const ts = map.timestamp;
            const formatted = `${ts.substring(0,4)}-${ts.substring(4,6)}-${ts.substring(6,8)} ${ts.substring(9,11)}:${ts.substring(11,13)}`;
            option.textContent = formatted;
        } else {
            option.textContent = map.filename;
        }
        
        select.appendChild(option);
    });
    
    log(`Populated dropdown with ${maps.length} date ranges`);
}

/**
 * Update info panel with current map details
 */
function updateInfoPanel(map) {
    const paramEl = document.getElementById('current-parameter');
    const dateEl = document.getElementById('current-date');
    const unitEl = document.getElementById('current-unit');
    
    if (!map) {
        if (paramEl) paramEl.textContent = '-';
        if (dateEl) dateEl.textContent = '-';
        if (unitEl) unitEl.classList.add('d-none');
        return;
    }
    
    if (paramEl) paramEl.textContent = map.display_name || map.parameter;
    if (dateEl) dateEl.textContent = map.date_range || 'No date range';
    if (unitEl) {
        unitEl.textContent = map.unit || '';
        if (map.unit) {
            unitEl.classList.remove('d-none');
        } else {
            unitEl.classList.add('d-none');
        }
    }
}

/**
 * Load map into iframe
 */
function loadMap(filename) {
    log(`Loading map: ${filename}`);
    
    const iframe = document.getElementById('map-iframe');
    const statusBadge = document.getElementById('map-status');
    
    if (!iframe) return;
    
    // Show loading state
    if (statusBadge) {
        statusBadge.className = 'badge bg-warning text-dark';
        statusBadge.textContent = 'Loading...';
    }
    
    // Find the selected map to get metadata
    const selectedMap = DashboardState.maps.find(m => m.filename === filename);
    const isAllParams = selectedMap && selectedMap.parameter === 'all_params';
    
    // For all_params maps, always use district_all_param directory
    let path;
    if (isAllParams) {
        // 修改此处
        path = `maps/output/district_all_param/${filename}`;
    } else {
        // Determine the correct path based on view type
        const viewType = DashboardState.viewType || 'district';
        
        // Adjust filename based on view type
        let adjustedFilename = filename;
        if (viewType === 'detailed' && filename.includes('_district_map.html')) {
            adjustedFilename = filename.replace('_district_map.html', '_detailed_map.html');
        } else if (viewType === 'district' && filename.includes('_detailed_map.html')) {
            adjustedFilename = filename.replace('_detailed_map.html', '_district_map.html');
        }
        // 修改此处
        path = `maps/output/${viewType}/${adjustedFilename}`;
    }
    
    // Set iframe source
    iframe.src = path;
    
    // Handle iframe load event
    iframe.onload = () => {
        log(`Map loaded successfully: ${filename}`);
        if (statusBadge) {
            statusBadge.className = 'badge bg-success';
            statusBadge.textContent = 'Ready';
        }
    };
    
    // Handle iframe error
    iframe.onerror = () => {
        log(`Error loading map: ${filename}`, 'error');
        if (statusBadge) {
            statusBadge.className = 'badge bg-danger';
            statusBadge.textContent = 'Error';
        }
    };
}

// ==========================================
// Event Handlers
// ==========================================

/**
 * Handle parameter selection change
 */
function handleParameterChange(event) {
    const parameter = event.target.value;
    log(`Parameter changed to: ${parameter}`);
    
    DashboardState.selectedParameter = parameter;
    
    // Update date range dropdown
    populateDateRangeDropdown(parameter);
    
    // Clear current map selection
    DashboardState.selectedMap = null;
    DashboardState.selectedDateRange = null;
    updateInfoPanel(null);
    
    // Hide map section until date is selected
    const mapSection = document.getElementById('map-section');
    if (mapSection) {
        mapSection.classList.add('d-none');
    }
    
    // Handle view type toggle for all_params (only district view available)
    updateViewTypeToggle(parameter);
}

/**
 * Update view type toggle state based on selected parameter
 * Disables "Detailed" option for all_params since it only has district maps
 */
function updateViewTypeToggle(parameter) {
    const viewDetailedRadio = document.getElementById('view-detailed');
    const viewDistrictRadio = document.getElementById('view-district');
    const detailedLabel = document.querySelector('label[for="view-detailed"]');
    
    if (parameter === 'all_params') {
        // Force district view and disable detailed option
        DashboardState.viewType = 'district';
        if (viewDistrictRadio) viewDistrictRadio.checked = true;
        if (viewDetailedRadio) viewDetailedRadio.disabled = true;
        if (detailedLabel) {
            detailedLabel.classList.add('disabled');
            detailedLabel.style.opacity = '0.5';
            detailedLabel.style.pointerEvents = 'none';
            detailedLabel.title = 'Detailed view not available for All Parameters';
        }
    } else {
        // Re-enable detailed option
        if (viewDetailedRadio) viewDetailedRadio.disabled = false;
        if (detailedLabel) {
            detailedLabel.classList.remove('disabled');
            detailedLabel.style.opacity = '';
            detailedLabel.style.pointerEvents = '';
            detailedLabel.title = '';
        }
    }
}

/**
 * Handle date range selection change
 */
function handleDateRangeChange(event) {
    const filename = event.target.value;
    log(`Date range changed to: ${filename}`);
    
    // Find the selected map
    const map = DashboardState.maps.find(m => m.filename === filename);
    
    if (map) {
        DashboardState.selectedMap = map;
        DashboardState.selectedDateRange = map.date_range || map.timestamp;
        
        // Update info panel
        updateInfoPanel(map);
        
        // Show map section
        const mapSection = document.getElementById('map-section');
        if (mapSection) {
            mapSection.classList.remove('d-none');
        }
        
        // Load the map
        loadMap(filename);
    }
}

/**
 * Handle view type toggle change
 */
function handleViewTypeChange(event) {
    const viewType = event.target.value;
    log(`View type changed to: ${viewType}`);
    
    // Prevent switching to detailed view for all_params
    if (DashboardState.selectedParameter === 'all_params' && viewType === 'detailed') {
        log('Detailed view not available for all_params, reverting to district', 'warn');
        const viewDistrictRadio = document.getElementById('view-district');
        if (viewDistrictRadio) viewDistrictRadio.checked = true;
        DashboardState.viewType = 'district';
        return;
    }
    
    DashboardState.viewType = viewType;
    
    // Reload current map with new view type if a map is selected
    if (DashboardState.selectedMap) {
        loadMap(DashboardState.selectedMap.filename);
    }
}

// ==========================================
// Initialization
// ==========================================

/**
 * Select default parameter and date on page load
 */
function selectDefaultOptions() {
    log('Selecting default options...');
    
    const parameterSelect = document.getElementById('parameter-select');
    const dateRangeSelect = document.getElementById('date-range-select');
    
    if (!parameterSelect || !dateRangeSelect) return;
    
    // Priority: all_params > cl2_free_1 > first available
    let defaultParam = null;
    if (DashboardState.parameters['all_params']) {
        defaultParam = 'all_params';
        log('All Parameters maps available, selecting as default');
    } else if (DashboardState.parameters['cl2_free_1']) {
        defaultParam = 'cl2_free_1';
        log('Chlorine maps available, selecting as default');
    }
    
    if (defaultParam) {
        log(`Found default parameter: ${defaultParam}`);
        
        // Select the parameter in dropdown
        parameterSelect.value = defaultParam;
        
        // Trigger the change event manually
        handleParameterChange({ target: { value: defaultParam } });
        
        // Select the first (latest) date range
        const maps = DashboardState.parameters[defaultParam];
        if (maps.length > 0) {
            const firstMap = maps[0];
            log(`Selecting default date range: ${firstMap.date_range || firstMap.timestamp}`);
            
            // Select in dropdown (after a short delay to allow dropdown to populate)
            setTimeout(() => {
                dateRangeSelect.value = firstMap.filename;
                handleDateRangeChange({ target: { value: firstMap.filename } });
            }, 100);
        }
    } else {
        log('No preferred parameter found, selecting first available parameter');
        
        // Select first available parameter
        const params = Object.keys(DashboardState.parameters).sort();
        if (params.length > 0) {
            const firstParam = params[0];
            parameterSelect.value = firstParam;
            handleParameterChange({ target: { value: firstParam } });
            
            // Select first date range
            const maps = DashboardState.parameters[firstParam];
            if (maps.length > 0) {
                setTimeout(() => {
                    dateRangeSelect.value = maps[0].filename;
                    handleDateRangeChange({ target: { value: maps[0].filename } });
                }, 100);
            }
        }
    }
}

/**
 * Initialize dashboard on page load
 */
async function initializeDashboard() {
    log('Initializing dashboard...');
    
    try {
        // Fetch maps data from API
        const data = await fetchMaps();
        
        // Process and store maps data
        processMapsData(data);
        
        // Update total maps count in header
        const totalMapsEl = document.getElementById('total-maps');
        if (totalMapsEl) {
            totalMapsEl.textContent = DashboardState.maps.length;
        }
        
        // Check if any maps are available
        if (DashboardState.maps.length === 0) {
            log('No maps available');
            showNoMapsMessage();
            hideLoading();
            return;
        }
        
        // Show controls section
        const controlsSection = document.getElementById('controls-section');
        if (controlsSection) {
            controlsSection.classList.remove('d-none');
        }
        
        // Populate dropdowns
        populateParameterDropdown();
        
        // Select default options (chlorine + latest date)
        selectDefaultOptions();
        
        // Show legend section
        const legendSection = document.getElementById('legend-section');
        if (legendSection) {
            legendSection.classList.remove('d-none');
        }
        
        log('Dashboard initialized successfully');
        
    } catch (error) {
        log(`Error initializing dashboard: ${error.message}`, 'error');
        showError(`Failed to load map data: ${error.message}`);
    } finally {
        hideLoading();
    }
}

// ==========================================
// Event Listeners
// ==========================================

/**
 * Attach event listeners after DOM is ready
 */
function attachEventListeners() {
    log('Attaching event listeners...');
    
    // Parameter dropdown change
    const paramSelect = document.getElementById('parameter-select');
    if (paramSelect) {
        paramSelect.addEventListener('change', handleParameterChange);
    }
    
    // Date range dropdown change
    const dateRangeSelect = document.getElementById('date-range-select');
    if (dateRangeSelect) {
        dateRangeSelect.addEventListener('change', handleDateRangeChange);
    }
    
    // View type toggle change
    const viewTypeRadios = document.querySelectorAll('input[name="view-type"]');
    viewTypeRadios.forEach(radio => {
        radio.addEventListener('change', handleViewTypeChange);
    });
    
    log('Event listeners attached');
}

// ==========================================
// DOM Ready - Start Application
// ==========================================

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    log('DOM loaded, starting dashboard...');
    attachEventListeners();
    initializeDashboard();
});
