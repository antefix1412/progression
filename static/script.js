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

    // Désactiver le bouton et afficher le chargement
    setLoading(true);
    updateInfoPanel('Chargement en cours...', 'info');
    
    try {
        const response = await fetch('/api/results');
        const contentType = response.headers.get('content-type') || '';
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`HTTP ${response.status}: ${errorText.slice(0, 160)}`);
        }

        let data;
        if (contentType.includes('application/json')) {
            data = await response.json();
        } else {
            const rawText = await response.text();
            try {
                data = JSON.parse(rawText);
            } catch (parseError) {
                throw new Error(`Réponse non JSON du serveur (début: ${rawText.slice(0, 80)})`);
            }
        }
        
        if (data.success) {
            const preparedResults = prepareResults(data.data);
            currentResults = preparedResults;
            displayResults(preparedResults);
            
            if (preparedResults.length === 0) {
                updateInfoPanel(`Aucun joueur affiche. API: ${data.count} joueur(s) charge(s) pour le club ${data.club || 'inconnu'}.`, 'warning');
                updateStatus('Aucun résultat trouvé');
            } else {
                updateInfoPanel(`${preparedResults.length} joueur(s) affiché(s) sur ${data.count} chargé(s)`, 'success');
                updateStatus(`${preparedResults.length} joueur(s) affiché(s)`);
            }
            
            // Activer le bouton copier
            copyBtn.disabled = preparedResults.length === 0;
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
            <td>${result.points_proposes}</td>
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
                <span class="card-label">Points proposes:</span>
                <span class="card-value">${result.points_proposes}</span>
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
    
    const header = "Licence\tPrénom\tNom\tPoints classement\tPoints proposes\tProgression";
    const separator = "-".repeat(80);
    const lines = [header, separator];
    
    currentResults.forEach(r => {
        const line = `${r.licence}\t${r.prenom}\t${r.nom}\t${r.points_classement}\t${r.points_proposes}\t${formatProgression(r.progression)}`;
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

function prepareResults(results) {
    const gain = parseMinProgression(ecartMinInput.value);

    return results
        .map(result => {
            const pointsClassement = toNumber(result.points_classement);
            const pointsProposes = toNumber(result.points_proposes);
            const progression = pointsClassement === null || pointsProposes === null
                ? null
                : pointsProposes - pointsClassement;

            return {
                ...result,
                points_classement: pointsClassement,
                points_proposes: pointsProposes,
                progression
            };
        })
        .filter(result => result.progression !== null)
        .filter(result => gain === null || result.progression >= gain)
        .sort((a, b) => b.progression - a.progression);
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

function parseMinProgression(value) {
    const trimmed = value.trim();
    if (!trimmed) {
        return null;
    }

    const parsed = Number(trimmed);
    return Number.isFinite(parsed) ? parsed : null;
}

function toNumber(value) {
    if (value === null || value === undefined || value === '') {
        return null;
    }

    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
}

function formatProgression(value) {
    return value >= 0 ? `+${value}` : `${value}`;
}

// Charger automatiquement au démarrage (optionnel)
// window.addEventListener('load', loadResults);
