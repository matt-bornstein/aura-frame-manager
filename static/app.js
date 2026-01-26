/**
 * Aura Frame Manager - Frontend Application
 */

// =============================================================================
// State Management
// =============================================================================

const state = {
    frames: [],
    currentFrameId: null,
    assets: [],
    filter: 'all',
    view: 'grid',
    searchQuery: '',
    selectedFiles: [],
    currentAsset: null,
};

// =============================================================================
// API Client
// =============================================================================

const api = {
    baseUrl: '',

    async request(endpoint, options = {}) {
        const url = `${this.baseUrl}${endpoint}`;
        const response = await fetch(url, {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers,
            },
            ...options,
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Request failed' }));
            throw new Error(error.detail || `HTTP ${response.status}`);
        }

        // Handle empty responses
        const text = await response.text();
        return text ? JSON.parse(text) : null;
    },

    // Frames
    async getFrames() {
        return this.request('/frames');
    },

    async getFrameStats(frameId) {
        return this.request(`/frames/${frameId}/stats`);
    },

    // Assets
    async getAssets(frameId, options = {}) {
        const params = new URLSearchParams();
        if (options.photosOnly) params.set('photos_only', 'true');
        if (options.videosOnly) params.set('videos_only', 'true');
        const query = params.toString() ? `?${params}` : '';
        return this.request(`/frames/${frameId}/assets${query}`);
    },

    async getAsset(frameId, assetId) {
        return this.request(`/frames/${frameId}/assets/${assetId}`);
    },

    async deleteAsset(frameId, assetId) {
        return this.request(`/frames/${frameId}/assets/${assetId}`, {
            method: 'DELETE',
        });
    },

    // Upload
    async uploadFile(frameId, file, caption = null) {
        const formData = new FormData();
        formData.append('file', file);
        
        const params = new URLSearchParams();
        if (caption) params.set('caption', caption);
        const query = params.toString() ? `?${params}` : '';

        const response = await fetch(`${this.baseUrl}/frames/${frameId}/upload${query}`, {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Upload failed' }));
            throw new Error(error.detail || `HTTP ${response.status}`);
        }

        return response.json();
    },

    async uploadFiles(frameId, files, caption = null) {
        const formData = new FormData();
        files.forEach(file => formData.append('files', file));

        const params = new URLSearchParams();
        if (caption) params.set('caption', caption);
        const query = params.toString() ? `?${params}` : '';

        const response = await fetch(`${this.baseUrl}/frames/${frameId}/upload/batch${query}`, {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Upload failed' }));
            throw new Error(error.detail || `HTTP ${response.status}`);
        }

        return response.json();
    },

    uploadFileWithProgress(frameId, file, caption = null, onProgress = null) {
        const formData = new FormData();
        formData.append('file', file);

        const params = new URLSearchParams();
        if (caption) params.set('caption', caption);
        const query = params.toString() ? `?${params}` : '';

        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            xhr.open('POST', `${this.baseUrl}/frames/${frameId}/upload${query}`);
            xhr.onload = () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    try {
                        resolve(xhr.responseText ? JSON.parse(xhr.responseText) : null);
                    } catch {
                        resolve(null);
                    }
                } else {
                    try {
                        const error = JSON.parse(xhr.responseText);
                        reject(new Error(error.detail || `HTTP ${xhr.status}`));
                    } catch {
                        reject(new Error(`HTTP ${xhr.status}`));
                    }
                }
            };
            xhr.onerror = () => reject(new Error('Upload failed'));
            if (xhr.upload && onProgress) {
                xhr.upload.onprogress = (event) => {
                    if (event.lengthComputable) {
                        const percent = Math.round((event.loaded / event.total) * 100);
                        onProgress(percent);
                    }
                };
            }
            xhr.send(formData);
        });
    },

    // Sync
    async syncFrames(sourceFrameId, targetFrameId, options = {}) {
        return this.request('/sync', {
            method: 'POST',
            body: JSON.stringify({
                source_frame_id: sourceFrameId,
                target_frame_id: targetFrameId,
                photos_only: options.photosOnly || false,
                videos_only: options.videosOnly || false,
                dry_run: options.dryRun || false,
            }),
        });
    },

    async syncSelectedFrames(frameIds, options = {}) {
        return this.request('/sync/selected', {
            method: 'POST',
            body: JSON.stringify({
                frame_ids: frameIds,
                dry_run: options.dryRun || false,
            }),
        });
    },

    // Metadata
    async fitAsset(frameId, assetId) {
        return this.request(`/frames/${frameId}/assets/${assetId}/crop`, {
            method: 'POST',
            body: JSON.stringify({ fit_to_frame: true }),
        });
    },

    async fitAllAssets(frameId, includeLandscape = false) {
        const params = new URLSearchParams();
        params.set('include_landscape', includeLandscape.toString());
        return this.request(`/frames/${frameId}/fit?${params}`, { method: 'POST' });
    },

    // Health
    async getHealth() {
        return this.request('/health');
    },

    // Download URL (full size)
    // Pass asset object to include metadata and avoid extra API calls on cache miss
    getDownloadUrl(frameId, asset) {
        const assetId = typeof asset === 'string' ? asset : asset.id;
        const params = new URLSearchParams();
        
        // If full asset object provided, include metadata to avoid backend API lookup
        if (typeof asset === 'object') {
            params.set('is_video', asset.is_video);
            params.set('user_id', asset.user_id);
            params.set('file_name', asset.file_name);
            if (asset.video_file_name) params.set('video_file_name', asset.video_file_name);
            if (asset.video_url) params.set('video_url', asset.video_url);
        }
        
        const query = params.toString() ? `?${params}` : '';
        return `${this.baseUrl}/frames/${frameId}/assets/${assetId}/download${query}`;
    },

    // Thumbnail URL (for grid/list views)
    // Pass asset object to include metadata and avoid extra API calls on cache miss
    getThumbnailUrl(frameId, asset) {
        const assetId = typeof asset === 'string' ? asset : asset.id;
        const params = new URLSearchParams();
        params.set('thumbnail', 'true');
        
        // If full asset object provided, include metadata to avoid backend API lookup
        if (typeof asset === 'object') {
            params.set('is_video', asset.is_video);
            params.set('user_id', asset.user_id);
            params.set('file_name', asset.file_name);
            if (asset.video_file_name) params.set('video_file_name', asset.video_file_name);
            if (asset.video_url) params.set('video_url', asset.video_url);
        }
        
        return `${this.baseUrl}/frames/${frameId}/assets/${assetId}/download?${params}`;
    },

    // Download All URL (returns zip file)
    getDownloadAllUrl(frameId, options = {}) {
        const params = new URLSearchParams();
        if (options.photosOnly) params.set('photos_only', 'true');
        if (options.videosOnly) params.set('videos_only', 'true');
        const query = params.toString() ? `?${params}` : '';
        return `${this.baseUrl}/frames/${frameId}/download/zip${query}`;
    },
};

// =============================================================================
// DOM Elements
// =============================================================================

const elements = {
    // Sidebar
    frameList: document.getElementById('frameList'),
    syncFramesBtn: document.getElementById('syncFramesBtn'),
    healthStatus: document.getElementById('healthStatus'),

    // Header
    pageTitle: document.getElementById('pageTitle'),
    pageSubtitle: document.getElementById('pageSubtitle'),
    headerActions: document.getElementById('headerActions'),
    refreshBtn: document.getElementById('refreshBtn'),
    downloadAllBtn: document.getElementById('downloadAllBtn'),
    downloadAllLoading: document.getElementById('downloadAllLoading'),
    fitAllBtn: document.getElementById('fitAllBtn'),
    uploadBtn: document.getElementById('uploadBtn'),

    // Stats
    statsBar: document.getElementById('statsBar'),
    statTotal: document.getElementById('statTotal'),
    statPhotos: document.getElementById('statPhotos'),
    statVideos: document.getElementById('statVideos'),
    statPortrait: document.getElementById('statPortrait'),
    statLandscape: document.getElementById('statLandscape'),

    // Filter
    filterBar: document.getElementById('filterBar'),
    searchInput: document.getElementById('searchInput'),

    // Content
    contentArea: document.getElementById('contentArea'),
    emptyState: document.getElementById('emptyState'),
    assetsGrid: document.getElementById('assetsGrid'),
    assetsList: document.getElementById('assetsList'),
    loadingState: document.getElementById('loadingState'),

    // Upload Modal
    uploadModal: document.getElementById('uploadModal'),
    uploadDropzone: document.getElementById('uploadDropzone'),
    fileInput: document.getElementById('fileInput'),
    browseFilesBtn: document.getElementById('browseFilesBtn'),
    uploadPreview: document.getElementById('uploadPreview'),
    uploadFileCount: document.getElementById('uploadFileCount'),
    previewList: document.getElementById('previewList'),
    clearFilesBtn: document.getElementById('clearFilesBtn'),
    uploadCaption: document.getElementById('uploadCaption'),
    closeUploadModal: document.getElementById('closeUploadModal'),
    cancelUploadBtn: document.getElementById('cancelUploadBtn'),
    startUploadBtn: document.getElementById('startUploadBtn'),

    // Sync Modal
    syncModal: document.getElementById('syncModal'),
    syncFrameList: document.getElementById('syncFrameList'),
    syncDryRun: document.getElementById('syncDryRun'),
    closeSyncModal: document.getElementById('closeSyncModal'),
    cancelSyncBtn: document.getElementById('cancelSyncBtn'),
    syncOnceBtn: document.getElementById('syncOnceBtn'),
    syncOutput: document.getElementById('syncOutput'),

    // Asset Modal
    assetModal: document.getElementById('assetModal'),
    assetModalTitle: document.getElementById('assetModalTitle'),
    assetPreviewContainer: document.getElementById('assetPreviewContainer'),
    assetDetailId: document.getElementById('assetDetailId'),
    assetDetailType: document.getElementById('assetDetailType'),
    assetDetailFilename: document.getElementById('assetDetailFilename'),
    assetDetailDimensions: document.getElementById('assetDetailDimensions'),
    assetDetailTakenAt: document.getElementById('assetDetailTakenAt'),
    closeAssetModal: document.getElementById('closeAssetModal'),
    deleteAssetBtn: document.getElementById('deleteAssetBtn'),
    fitAssetBtn: document.getElementById('fitAssetBtn'),
    downloadAssetBtn: document.getElementById('downloadAssetBtn'),

    // Toast
    toastContainer: document.getElementById('toastContainer'),
};

// =============================================================================
// Toast Notifications
// =============================================================================

function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span class="toast-message">${message}</span>
        <button class="toast-close">&times;</button>
    `;

    elements.toastContainer.appendChild(toast);

    const closeBtn = toast.querySelector('.toast-close');
    closeBtn.addEventListener('click', () => removeToast(toast));

    setTimeout(() => removeToast(toast), 5000);
}

function removeToast(toast) {
    toast.classList.add('removing');
    setTimeout(() => toast.remove(), 300);
}

// =============================================================================
// Loading States
// =============================================================================

function showLoading() {
    elements.emptyState.style.display = 'none';
    elements.assetsGrid.style.display = 'none';
    elements.assetsList.style.display = 'none';
    elements.loadingState.style.display = 'flex';
}

function hideLoading() {
    elements.loadingState.style.display = 'none';
}

// =============================================================================
// Frame Management
// =============================================================================

async function loadFrames() {
    try {
        const data = await api.getFrames();
        state.frames = data.frames;
        renderFrameList();
    } catch (error) {
        console.error('Failed to load frames:', error);
        showToast('Failed to load frames: ' + error.message, 'error');
    }
}

function renderFrameList() {
    elements.frameList.innerHTML = state.frames.map(frame => `
        <li class="frame-item">
            <a class="frame-link ${frame.frame_id === state.currentFrameId ? 'active' : ''}" 
               data-frame-id="${frame.frame_id}">
                <svg class="frame-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="3" y="3" width="18" height="18" rx="2"/>
                    <circle cx="8.5" cy="8.5" r="1.5"/>
                    <path d="M21 15l-5-5L5 21"/>
                </svg>
                <span class="frame-name">${frame.name}</span>
            </a>
        </li>
    `).join('');

    // Add click handlers
    elements.frameList.querySelectorAll('.frame-link').forEach(link => {
        link.addEventListener('click', () => {
            const frameId = link.dataset.frameId;
            selectFrame(frameId);
        });
    });
}

async function selectFrame(frameId, updateUrl = true) {
    state.currentFrameId = frameId;
    const frame = state.frames.find(f => f.frame_id === frameId);

    // Update URL with frame ID
    if (updateUrl) {
        const newUrl = `/${frameId}`;
        history.pushState({ frameId }, '', newUrl);
    }

    // Update UI
    elements.pageTitle.textContent = frame ? frame.name : 'Frame';
    elements.pageSubtitle.textContent = 'Loading assets...';
    elements.headerActions.style.display = 'flex';
    elements.statsBar.style.display = 'flex';
    elements.filterBar.style.display = 'flex';

    // Update sidebar active state
    renderFrameList();

    // Load assets
    await loadAssets();
    await loadStats();
}

async function loadStats() {
    if (!state.currentFrameId) return;

    try {
        const stats = await api.getFrameStats(state.currentFrameId);
        elements.statTotal.textContent = stats.total;
        elements.statPhotos.textContent = stats.photos;
        elements.statVideos.textContent = stats.videos;
        elements.statPortrait.textContent = stats.portrait;
        elements.statLandscape.textContent = stats.landscape;
    } catch (error) {
        console.error('Failed to load stats:', error);
    }
}

// =============================================================================
// Asset Management
// =============================================================================

async function loadAssets() {
    if (!state.currentFrameId) return;

    showLoading();

    try {
        const data = await api.getAssets(state.currentFrameId);
        state.assets = data.assets;
        elements.pageSubtitle.textContent = `${state.assets.length} assets`;
        renderAssets();
    } catch (error) {
        console.error('Failed to load assets:', error);
        showToast('Failed to load assets: ' + error.message, 'error');
        elements.emptyState.style.display = 'flex';
    } finally {
        hideLoading();
    }
}

function getFilteredAssets() {
    let filtered = state.assets;

    // Apply type filter
    if (state.filter === 'photos') {
        filtered = filtered.filter(a => !a.is_video);
    } else if (state.filter === 'videos') {
        filtered = filtered.filter(a => a.is_video);
    }

    // Apply search
    if (state.searchQuery) {
        const query = state.searchQuery.toLowerCase();
        filtered = filtered.filter(a => 
            a.file_name.toLowerCase().includes(query) ||
            a.id.toLowerCase().includes(query)
        );
    }

    return filtered;
}

function renderAssets() {
    const filtered = getFilteredAssets();

    if (filtered.length === 0) {
        elements.emptyState.style.display = 'flex';
        elements.assetsGrid.style.display = 'none';
        elements.assetsList.style.display = 'none';
        elements.emptyState.querySelector('h3').textContent = 'No assets found';
        elements.emptyState.querySelector('p').textContent = 
            state.searchQuery ? 'Try adjusting your search.' : 'Upload some photos or videos to get started.';
        return;
    }

    elements.emptyState.style.display = 'none';

    if (state.view === 'grid') {
        renderGridView(filtered);
    } else {
        renderListView(filtered);
    }
}

function renderGridView(assets) {
    elements.assetsList.style.display = 'none';
    elements.assetsGrid.style.display = 'grid';

    elements.assetsGrid.innerHTML = assets.map(asset => `
        <div class="asset-card" data-asset-id="${asset.id}">
            <div class="asset-thumbnail">
                ${asset.is_video ? `
                    <div class="asset-type-badge">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polygon points="5,3 19,12 5,21"/>
                        </svg>
                        Video
                    </div>
                ` : ''}
                <img src="${api.getThumbnailUrl(state.currentFrameId, asset)}" 
                     alt="${asset.file_name}"
                     loading="lazy"
                     onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 24 24%22 fill=%22%23cbd5e1%22><rect width=%2224%22 height=%2224%22/><text x=%2212%22 y=%2214%22 text-anchor=%22middle%22 font-size=%228%22 fill=%22%2394a3b8%22>?</text></svg>'">
            </div>
            <div class="asset-card-info">
                <div class="asset-card-name">${asset.id}</div>
                <div class="asset-card-meta">${asset.width} x ${asset.height}</div>
            </div>
        </div>
    `).join('');

    // Add click handlers
    elements.assetsGrid.querySelectorAll('.asset-card').forEach(card => {
        card.addEventListener('click', () => {
            const assetId = card.dataset.assetId;
            openAssetModal(assetId);
        });
    });
}

function renderListView(assets) {
    elements.assetsGrid.style.display = 'none';
    elements.assetsList.style.display = 'block';

    elements.assetsList.innerHTML = assets.map(asset => `
        <div class="asset-row" data-asset-id="${asset.id}">
            <div class="asset-row-thumbnail">
                <img src="${api.getThumbnailUrl(state.currentFrameId, asset)}" 
                     alt="${asset.file_name}"
                     loading="lazy"
                     onerror="this.style.display='none'">
            </div>
            <div class="asset-row-info">
                <div class="asset-row-name">${asset.id}</div>
                <div class="asset-row-meta">${asset.width} x ${asset.height} ${asset.taken_at ? ' • ' + formatDate(asset.taken_at) : ''}</div>
            </div>
            <span class="asset-row-type ${asset.is_video ? 'video' : ''}">${asset.is_video ? 'Video' : 'Photo'}</span>
        </div>
    `).join('');

    // Add click handlers
    elements.assetsList.querySelectorAll('.asset-row').forEach(row => {
        row.addEventListener('click', () => {
            const assetId = row.dataset.assetId;
            openAssetModal(assetId);
        });
    });
}

function formatDate(dateString) {
    if (!dateString) return '-';
    try {
        return new Date(dateString).toLocaleDateString();
    } catch {
        return dateString;
    }
}

// =============================================================================
// Asset Modal
// =============================================================================

function openAssetModal(assetId, updateUrl = true) {
    const asset = state.assets.find(a => a.id === assetId);
    if (!asset) return;

    state.currentAsset = asset;

    // Update URL with asset ID
    if (updateUrl && state.currentFrameId) {
        const newUrl = `/${state.currentFrameId}/${assetId}`;
        history.pushState({ frameId: state.currentFrameId, assetId }, '', newUrl);
    }

    // Update modal content
    elements.assetModalTitle.textContent = asset.is_video ? 'Video Details' : 'Photo Details';
    elements.assetDetailId.textContent = asset.id;
    elements.assetDetailType.textContent = asset.is_video ? 'Video' : 'Photo';
    elements.assetDetailFilename.textContent = asset.is_video ? asset.video_file_name : asset.file_name;
    elements.assetDetailDimensions.textContent = `${asset.width} x ${asset.height}`;
    elements.assetDetailTakenAt.textContent = formatDate(asset.taken_at);

    // Show preview
    if (asset.is_video) {
        elements.assetPreviewContainer.innerHTML = `
            <video controls style="max-width:100%;max-height:100%;">
                <source src="${api.getDownloadUrl(state.currentFrameId, asset)}" type="video/mp4">
            </video>
        `;
    } else {
        elements.assetPreviewContainer.innerHTML = `
            <img src="${api.getDownloadUrl(state.currentFrameId, asset)}" alt="${asset.file_name}">
        `;
    }

    elements.assetModal.classList.add('open');
}

function closeAssetModal(updateUrl = true) {
    elements.assetModal.classList.remove('open');
    state.currentAsset = null;

    // Update URL to remove asset ID (back to frame-only)
    if (updateUrl && state.currentFrameId) {
        const newUrl = `/${state.currentFrameId}`;
        history.pushState({ frameId: state.currentFrameId }, '', newUrl);
    }
}

async function deleteCurrentAsset() {
    if (!state.currentAsset || !state.currentFrameId) return;

    if (!confirm(`Are you sure you want to delete "${state.currentAsset.file_name}"?`)) {
        return;
    }

    try {
        await api.deleteAsset(state.currentFrameId, state.currentAsset.id);
        showToast('Asset deleted successfully');
        closeAssetModal();
        await loadAssets();
        await loadStats();
    } catch (error) {
        console.error('Failed to delete asset:', error);
        showToast('Failed to delete asset: ' + error.message, 'error');
    }
}

async function fitCurrentAsset() {
    if (!state.currentAsset || !state.currentFrameId) return;

    try {
        await api.fitAsset(state.currentFrameId, state.currentAsset.id);
        showToast('Asset fitted successfully');
    } catch (error) {
        console.error('Failed to fit asset:', error);
        showToast('Failed to fit asset: ' + error.message, 'error');
    }
}

function downloadCurrentAsset() {
    if (!state.currentAsset || !state.currentFrameId) return;

    const url = api.getDownloadUrl(state.currentFrameId, state.currentAsset);
    const a = document.createElement('a');
    a.href = url;
    a.download = state.currentAsset.file_name;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

// =============================================================================
// Upload Modal
// =============================================================================

function openUploadModal() {
    if (!state.currentFrameId) {
        showToast('Please select a frame first', 'warning');
        return;
    }
    state.selectedFiles = [];
    updateUploadPreview();
    elements.uploadCaption.value = '';
    elements.uploadModal.classList.add('open');
}

function closeUploadModal() {
    elements.uploadModal.classList.remove('open');
    state.selectedFiles = [];
    elements.fileInput.value = '';
}

function handleFileSelect(files) {
    const validTypes = ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/heic',
                        'video/mp4', 'video/quicktime', 'video/x-msvideo', 'video/webm'];
    
    for (const file of files) {
        if (validTypes.some(type => file.type.startsWith(type.split('/')[0]))) {
            state.selectedFiles.push(file);
        }
    }
    
    updateUploadPreview();
}

function updateUploadPreview() {
    if (state.selectedFiles.length === 0) {
        elements.uploadDropzone.style.display = 'block';
        elements.uploadPreview.style.display = 'none';
        elements.startUploadBtn.disabled = true;
        return;
    }

    elements.uploadDropzone.style.display = 'none';
    elements.uploadPreview.style.display = 'block';
    elements.startUploadBtn.disabled = false;
    elements.uploadFileCount.textContent = `${state.selectedFiles.length} file${state.selectedFiles.length > 1 ? 's' : ''} selected`;

    elements.previewList.innerHTML = state.selectedFiles.map((file, index) => `
        <div class="preview-item" data-index="${index}">
            <div class="preview-item-thumb">
                ${file.type.startsWith('image/') ? 
                    `<img src="${URL.createObjectURL(file)}" alt="${file.name}">` : 
                    ''}
            </div>
            <div class="preview-item-info">
                <div class="preview-item-name">${file.name}</div>
                <div class="preview-item-size">${formatFileSize(file.size)}</div>
                <div class="preview-item-status status-queued">Queued</div>
                <div class="preview-item-progress">
                    <div class="preview-item-progress-bar" style="width: 0%;"></div>
                </div>
            </div>
            <button class="preview-item-remove" data-index="${index}">&times;</button>
        </div>
    `).join('');

    // Add remove handlers
    elements.previewList.querySelectorAll('.preview-item-remove').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const index = parseInt(btn.dataset.index);
            state.selectedFiles.splice(index, 1);
            updateUploadPreview();
        });
    });
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function setPreviewStatus(index, text, statusClass) {
    const item = elements.previewList.querySelector(`.preview-item[data-index="${index}"]`);
    if (!item) return;
    const status = item.querySelector('.preview-item-status');
    if (!status) return;
    status.textContent = text;
    status.className = `preview-item-status ${statusClass}`;
}

function setPreviewProgress(index, percent) {
    const item = elements.previewList.querySelector(`.preview-item[data-index="${index}"]`);
    if (!item) return;
    const bar = item.querySelector('.preview-item-progress-bar');
    if (!bar) return;
    bar.style.width = `${percent}%`;
}

async function startUpload() {
    if (state.selectedFiles.length === 0 || !state.currentFrameId) return;

    const btnText = elements.startUploadBtn.querySelector('.btn-text');
    const btnLoading = elements.startUploadBtn.querySelector('.btn-loading');
    
    btnText.style.display = 'none';
    btnLoading.style.display = 'flex';
    elements.startUploadBtn.disabled = true;
    elements.cancelUploadBtn.disabled = true;
    elements.fileInput.disabled = true;
    elements.browseFilesBtn.disabled = true;
    elements.clearFilesBtn.disabled = true;

    const caption = elements.uploadCaption.value || null;
    let uploaded = 0;
    let failed = 0;

    try {
        for (let i = 0; i < state.selectedFiles.length; i++) {
            const file = state.selectedFiles[i];
            setPreviewStatus(i, 'Uploading...', 'status-uploading');
            try {
                await api.uploadFileWithProgress(
                    state.currentFrameId,
                    file,
                    caption,
                    (percent) => setPreviewProgress(i, percent)
                );
                setPreviewProgress(i, 100);
                setPreviewStatus(i, 'Uploaded', 'status-success');
                uploaded++;
            } catch (error) {
                console.error(`Failed to upload ${file.name}:`, error);
                setPreviewStatus(i, 'Failed', 'status-error');
                failed++;
            }
        }
    } finally {
        closeUploadModal();
        await loadAssets();
        await loadStats();
    }

    btnText.style.display = 'inline';
    btnLoading.style.display = 'none';
    elements.startUploadBtn.disabled = false;
    elements.cancelUploadBtn.disabled = false;
    elements.fileInput.disabled = false;
    elements.browseFilesBtn.disabled = false;
    elements.clearFilesBtn.disabled = false;

    if (failed === 0) {
        showToast(`Successfully uploaded ${uploaded} file${uploaded > 1 ? 's' : ''}`);
    } else if (uploaded === 0) {
        showToast(`Upload failed (${failed} file${failed > 1 ? 's' : ''})`, 'error');
    } else {
        showToast(`Uploaded ${uploaded}, failed ${failed}`, 'warning');
    }

    // Refresh happens in finally
}

// =============================================================================
// Sync Modal
// =============================================================================

function openSyncModal() {
    renderSyncFrameList();
    elements.syncDryRun.checked = false;
    elements.syncOutput.value = '';
    updateSyncControls();
    elements.syncModal.classList.add('open');
}

function closeSyncModal() {
    elements.syncModal.classList.remove('open');
}

function renderSyncFrameList() {
    elements.syncFrameList.innerHTML = state.frames.map(frame => `
        <label class="checkbox-label sync-frame-item">
            <input type="checkbox" data-frame-id="${frame.frame_id}">
            <span>${frame.name}</span>
        </label>
    `).join('');

    elements.syncFrameList.querySelectorAll('input[type="checkbox"]').forEach(input => {
        input.addEventListener('change', updateSyncControls);
    });
}

function getSelectedSyncFrameIds() {
    return Array.from(
        elements.syncFrameList.querySelectorAll('input[type="checkbox"]:checked')
    ).map(input => input.dataset.frameId);
}

function updateSyncControls() {
    const selectedCount = getSelectedSyncFrameIds().length;
    const enabled = selectedCount >= 2;
    elements.syncDryRun.disabled = !enabled;
    elements.syncOnceBtn.disabled = !enabled;
    if (!enabled) {
        elements.syncDryRun.checked = false;
    }
}

function setSyncOutput(lines) {
    elements.syncOutput.value = lines.join('\n');
    elements.syncOutput.scrollTop = elements.syncOutput.scrollHeight;
}

function setSyncInputsDisabled(disabled) {
    elements.syncFrameList.querySelectorAll('input[type="checkbox"]').forEach(input => {
        input.disabled = disabled;
    });
    elements.syncDryRun.disabled = disabled;
    elements.syncOnceBtn.disabled = disabled;
}

async function startSync() {
    const selectedIds = getSelectedSyncFrameIds();
    if (selectedIds.length < 2) {
        return;
    }

    const btnText = elements.syncOnceBtn.querySelector('.btn-text');
    const btnLoading = elements.syncOnceBtn.querySelector('.btn-loading');
    const dryRun = elements.syncDryRun.checked;

    btnText.style.display = 'none';
    btnLoading.style.display = 'flex';
    setSyncInputsDisabled(true);

    setSyncOutput([
        `${dryRun ? 'Dry run' : 'Sync'} started...`,
        `Frames: ${selectedIds.join(', ')}`,
        '',
        'Waiting for results...'
    ]);

    try {
        const result = await api.syncSelectedFrames(selectedIds, { dryRun });
        const lines = Array.isArray(result.lines) ? result.lines : [result.message];
        setSyncOutput(lines);
        showToast(result.message);

        if (!dryRun && state.currentFrameId && selectedIds.includes(state.currentFrameId)) {
            await loadAssets();
            await loadStats();
        }
    } catch (error) {
        console.error('Sync failed:', error);
        setSyncOutput([`Sync failed: ${error.message}`]);
        showToast('Sync failed: ' + error.message, 'error');
    } finally {
        btnText.style.display = 'inline';
        btnLoading.style.display = 'none';
        setSyncInputsDisabled(false);
        updateSyncControls();
    }
}

// =============================================================================
// Health Check
// =============================================================================

async function checkHealth() {
    const statusDot = elements.healthStatus.querySelector('.status-dot');
    const statusText = elements.healthStatus.querySelector('.status-text');

    try {
        const health = await api.getHealth();
        statusDot.className = 'status-dot ' + (health.aura_initialized ? 'healthy' : 'error');
        statusText.textContent = health.aura_initialized ? 
            `Connected (${health.frames_configured} frames)` : 
            'Not initialized';
    } catch (error) {
        statusDot.className = 'status-dot error';
        statusText.textContent = 'Disconnected';
    }
}

// =============================================================================
// Fit All
// =============================================================================

async function fitAllAssets() {
    if (!state.currentFrameId) return;

    if (!confirm('This will fit all images on this frame to show the complete picture (removes auto-crop). Continue?')) {
        return;
    }

    try {
        const result = await api.fitAllAssets(state.currentFrameId, true);
        showToast(result.message);
    } catch (error) {
        console.error('Fit all failed:', error);
        showToast('Failed to fit assets: ' + error.message, 'error');
    }
}

// =============================================================================
// Download All
// =============================================================================

async function downloadAllAssets() {
    if (!state.currentFrameId) return;

    const assetCount = state.assets.length;
    if (assetCount === 0) {
        showToast('No assets to download', 'warning');
        return;
    }

    if (!confirm(`This will download ${assetCount} assets as a ZIP file. This may take a while. Continue?`)) {
        return;
    }

    // Show loading state
    const btnText = elements.downloadAllBtn.querySelector('.btn-text');
    const btnLoading = elements.downloadAllLoading;
    btnText.style.display = 'none';
    btnLoading.style.display = 'flex';
    elements.downloadAllBtn.disabled = true;

    showToast('Preparing download... This may take a few minutes for large collections.', 'success');

    try {
        // Create a hidden link and trigger download
        const url = api.getDownloadAllUrl(state.currentFrameId);
        
        // Use fetch to handle the download so we can show proper errors
        const response = await fetch(url);
        
        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Download failed' }));
            throw new Error(error.detail || `HTTP ${response.status}`);
        }
        
        // Get the filename from Content-Disposition header or use default
        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = 'assets.zip';
        if (contentDisposition) {
            const match = contentDisposition.match(/filename="?([^";\n]+)"?/);
            if (match) filename = match[1];
        }
        
        // Create blob and download
        const blob = await response.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = downloadUrl;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(downloadUrl);
        
        showToast('Download started! Check your downloads folder.', 'success');
    } catch (error) {
        console.error('Download all failed:', error);
        showToast('Failed to download assets: ' + error.message, 'error');
    } finally {
        // Reset button state
        btnText.style.display = 'inline';
        btnLoading.style.display = 'none';
        elements.downloadAllBtn.disabled = false;
    }
}

// =============================================================================
// Event Listeners
// =============================================================================

function initEventListeners() {
    // Header actions
    elements.refreshBtn.addEventListener('click', async () => {
        await loadAssets();
        await loadStats();
        showToast('Refreshed');
    });

    elements.downloadAllBtn.addEventListener('click', downloadAllAssets);
    elements.fitAllBtn.addEventListener('click', fitAllAssets);
    elements.uploadBtn.addEventListener('click', openUploadModal);
    
    // Sync frames button
    elements.syncFramesBtn.addEventListener('click', openSyncModal);

    // Filter buttons
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            state.filter = btn.dataset.filter;
            renderAssets();
        });
    });

    // View toggle
    document.querySelectorAll('.view-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.view-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            state.view = btn.dataset.view;
            renderAssets();
        });
    });

    // Search
    elements.searchInput.addEventListener('input', (e) => {
        state.searchQuery = e.target.value;
        renderAssets();
    });

    // Upload modal
    elements.closeUploadModal.addEventListener('click', closeUploadModal);
    elements.cancelUploadBtn.addEventListener('click', closeUploadModal);
    elements.browseFilesBtn.addEventListener('click', () => elements.fileInput.click());
    elements.fileInput.addEventListener('change', (e) => handleFileSelect(e.target.files));
    elements.clearFilesBtn.addEventListener('click', () => {
        state.selectedFiles = [];
        updateUploadPreview();
    });
    elements.startUploadBtn.addEventListener('click', startUpload);

    // Drag and drop
    elements.uploadDropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        elements.uploadDropzone.classList.add('dragover');
    });
    elements.uploadDropzone.addEventListener('dragleave', () => {
        elements.uploadDropzone.classList.remove('dragover');
    });
    elements.uploadDropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        elements.uploadDropzone.classList.remove('dragover');
        handleFileSelect(e.dataTransfer.files);
    });

    // Sync modal
    elements.closeSyncModal.addEventListener('click', closeSyncModal);
    elements.cancelSyncBtn.addEventListener('click', closeSyncModal);
    elements.syncOnceBtn.addEventListener('click', startSync);

    // Asset modal
    elements.closeAssetModal.addEventListener('click', closeAssetModal);
    elements.deleteAssetBtn.addEventListener('click', deleteCurrentAsset);
    elements.fitAssetBtn.addEventListener('click', fitCurrentAsset);
    elements.downloadAssetBtn.addEventListener('click', downloadCurrentAsset);

    // Modal backdrop clicks
    document.querySelectorAll('.modal-backdrop').forEach(backdrop => {
        backdrop.addEventListener('click', () => {
            backdrop.closest('.modal').classList.remove('open');
        });
    });

    // Escape key to close modals
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            document.querySelectorAll('.modal.open').forEach(modal => {
                modal.classList.remove('open');
            });
        }
    });
}

// =============================================================================
// URL / Deep Linking
// =============================================================================

function getIdsFromUrl() {
    const path = window.location.pathname;
    // Extract frame ID and optional asset ID from path like "/<frame_id>" or "/<frame_id>/<asset_id>"
    const match = path.match(/^\/([a-f0-9-]+)(?:\/([a-f0-9-]+))?$/i);
    return {
        frameId: match ? match[1] : null,
        assetId: match ? match[2] : null
    };
}

async function handlePopState(event) {
    const { frameId, assetId } = event.state || getIdsFromUrl();
    
    if (frameId && state.frames.some(f => f.frame_id === frameId)) {
        // If frame changed, select it
        if (frameId !== state.currentFrameId) {
            await selectFrame(frameId, false);
        }
        
        // Handle asset modal state
        if (assetId) {
            // Open asset modal if we have the asset loaded
            const asset = state.assets.find(a => a.id === assetId);
            if (asset) {
                openAssetModal(assetId, false);
            }
        } else {
            // Close asset modal if open
            if (state.currentAsset) {
                closeAssetModal(false);
            }
        }
    } else if (!frameId) {
        // Navigated back to root - clear selection
        if (state.currentAsset) {
            closeAssetModal(false);
        }
        state.currentFrameId = null;
        elements.pageTitle.textContent = 'Select a Frame';
        elements.pageSubtitle.textContent = 'Choose a frame from the sidebar to manage its assets';
        elements.headerActions.style.display = 'none';
        elements.statsBar.style.display = 'none';
        elements.filterBar.style.display = 'none';
        elements.emptyState.style.display = 'flex';
        elements.assetsGrid.style.display = 'none';
        elements.assetsList.style.display = 'none';
        renderFrameList();
    }
}

// =============================================================================
// Initialization
// =============================================================================

async function init() {
    initEventListeners();
    await checkHealth();
    await loadFrames();
    
    // Handle browser back/forward navigation
    window.addEventListener('popstate', handlePopState);
    
    // Check URL for deep link to frame and/or asset
    const { frameId, assetId } = getIdsFromUrl();
    if (frameId && state.frames.some(f => f.frame_id === frameId)) {
        await selectFrame(frameId, false);
        
        // If asset ID in URL, open its modal after assets are loaded
        if (assetId) {
            const asset = state.assets.find(a => a.id === assetId);
            if (asset) {
                openAssetModal(assetId, false);
            }
        }
    }
    
    // Check health periodically
    setInterval(checkHealth, 30000);
}

// Start the app
init();
