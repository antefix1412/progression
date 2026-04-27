// Variables globales
let currentResults = [];

// Éléments DOM
const loadBtn = document.getElementById('loadBtn');
const copyBtn = document.getElementById('copyBtn');
const resultsBody = document.getElementById('resultsBody');
const infoPanel = document.getElementById('infoPanel');
const infoText = document.getElementById('infoText');
const loadingSpinner = document.getElementById('loadingSpinner');
const statusDiv = document.getElementById('status');
const ecartMinInput = document.getElementById('ecartMin');

// Event Listeners
loadBtn.addEventListener('click', loadResults);
copyBtn.addEventListener('click', copyAllResults);

// Fonction pour charger les résultats
async function loadResults() {
    if (loadBtn.disabled) return;
    
    // Récupérer le seuil de progression
    const gain = ecartMinInput.value.trim();
    
    // Désactiver le bouton et afficher le chargement
    setLoading(true);
    updateInfoPanel('Chargement en cours...', 'info');
    
    try {
        const query = gain ? `?gain=${encodeURIComponent(gain)}` : '';
        const response = await fetch(`/api/results${query}`);
        const data = await response.json();
        
        if (data.success) {
            currentResults = data.data;
            displayResults(data.data);
            
            if (data.count === 0) {
                updateInfoPanel('Aucun joueur ne correspond au filtre en cours.', 'warning');
                updateStatus('Aucun résultat trouvé');
            } else {
                updateInfoPanel(`${data.count} joueur(s) chargé(s) avec leur progression mensuelle`, 'success');
                updateStatus(`${data.count} joueur(s) chargé(s)`);
            }
            
            // Activer le bouton copier
            copyBtn.disabled = data.count === 0;
        } else {
            updateInfoPanel(`Erreur: ${data.error}`, 'error');
            updateStatus('Erreur lors du chargement');
        }
    } catch (error) {
        console.error('Erreur:', error);
        updateInfoPanel(`Erreur de connexion: ${error.message}`, 'error');
        updateStatus('Erreur de connexion');
    } finally {
        setLoading(false);
    }
}

// Fonction pour afficher les résultats dans le tableau
function displayResults(results) {
    const mobileResults = document.getElementById('mobileResults');
    resultsBody.innerHTML = '';
    mobileResults.innerHTML = '';
    
    if (results.length === 0) {
        resultsBody.innerHTML = '<tr><td colspan="6" class="empty-state">Aucune donnée à afficher</td></tr>';
        mobileResults.innerHTML = '<p style="text-align: center; color: #6c757d; font-style: italic; padding: 20px;">Aucune donnée à afficher</p>';
        return;
    }
    
    results.forEach((result, index) => {
        // Affichage tableau desktop
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${escapeHtml(result.licence)}</td>
            <td>${escapeHtml(result.prenom)}</td>
            <td>${escapeHtml(result.nom)}</td>
            <td>${result.points_classement}</td>
            <td>${result.points_mensuels}</td>
            <td><span class="ecart-badge">${formatProgression(result.progression)}</span></td>
        `;
        resultsBody.appendChild(row);
        
        // Affichage cartes mobile
        const card = document.createElement('div');
        card.className = 'result-card';
        card.innerHTML = `
            <div class="card-row">
                <span class="card-label">Licence:</span>
                <span class="card-value">${escapeHtml(result.licence)}</span>
            </div>
            <div class="card-row">
                <span class="card-label">Joueur:</span>
                <span class="card-value">${escapeHtml(result.prenom)} ${escapeHtml(result.nom)}</span>
            </div>
            <div class="card-row">
                <span class="card-label">Points classement:</span>
                <span class="card-value">${result.points_classement}</span>
            </div>
            <div class="card-row">
                <span class="card-label">Points mensuels:</span>
                <span class="card-value">${result.points_mensuels}</span>
            </div>
            <div class="card-row">
                <span class="card-label">Progression:</span>
                <span class="card-value"><span class="ecart-badge">${formatProgression(result.progression)}</span></span>
            </div>
        `;
        mobileResults.appendChild(card);
    });
}

// Fonction pour copier tous les résultats
function copyAllResults() {
    if (currentResults.length === 0) return;
    
    const header = "Licence\tPrénom\tNom\tPoints classement\tPoints mensuels\tProgression";
    const separator = "-".repeat(80);
    const lines = [header, separator];
    
    currentResults.forEach(r => {
        const line = `${r.licence}\t${r.prenom}\t${r.nom}\t${r.points_classement}\t${r.points_mensuels}\t${formatProgression(r.progression)}`;
        lines.push(line);
    });
    
    const text = lines.join('\n');
    
    // Copier dans le presse-papier
    navigator.clipboard.writeText(text).then(() => {
        updateStatus('Tableau copié dans le presse-papier');
    }).catch(err => {
        console.error('Erreur lors de la copie:', err);
        updateStatus('Erreur lors de la copie');
    });
}

// Fonctions utilitaires
function setLoading(loading) {
    if (loading) {
        loadBtn.disabled = true;
        loadBtn.innerHTML = '<span class="btn-icon">⏳</span> Chargement...';
        loadingSpinner.style.display = 'block';
    } else {
        loadBtn.disabled = false;
        loadBtn.innerHTML = '<span class="btn-icon">🔄</span> Charger les Joueurs';
        loadingSpinner.style.display = 'none';
    }
}

function updateInfoPanel(message, type = 'info') {
    infoText.textContent = message;
    infoPanel.className = 'info-panel';
    
    if (type === 'success') {
        infoPanel.classList.add('success');
    } else if (type === 'warning') {
        infoPanel.classList.add('warning');
    } else if (type === 'error') {
        infoPanel.classList.add('error');
    }
}

function updateStatus(message) {
    statusDiv.textContent = message;
    
    // Réinitialiser après 3 secondes
    setTimeout(() => {
        statusDiv.textContent = 'Prêt';
    }, 3000);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatProgression(value) {
    return value >= 0 ? `+${value}` : `${value}`;
}

// Charger automatiquement au démarrage (optionnel)
// window.addEventListener('load', loadResults);
