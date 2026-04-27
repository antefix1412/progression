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
    
    // Récupérer l'écart
    const ecart = ecartMinInput.value.trim() || '75';
    
    // Désactiver le bouton et afficher le chargement
    setLoading(true);
    updateInfoPanel('Chargement en cours...', 'info');
    
    try {
        const response = await fetch(`/api/results?ecart=${encodeURIComponent(ecart)}`);
        const data = await response.json();
        
        if (data.success) {
            currentResults = data.data;
            displayResults(data.data);
            
            if (data.count === 0) {
                updateInfoPanel('Aucune performance exceptionnelle trouvée.', 'warning');
                updateStatus('Aucun résultat trouvé');
            } else {
                updateInfoPanel(`${data.count} performance(s) exceptionnelle(s) trouvée(s)`, 'success');
                updateStatus(`${data.count} performance(s) chargée(s)`);
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
            <td>${escapeHtml(result.date)}</td>
            <td>${escapeHtml(result.prenom)}</td>
            <td>${escapeHtml(result.nom)}</td>
            <td>${result.points_joueur}</td>
            <td>${result.points_adv}</td>
            <td><span class="ecart-badge">+${result.ecart}</span></td>
        `;
        resultsBody.appendChild(row);
        
        // Affichage cartes mobile
        const card = document.createElement('div');
        card.className = 'result-card';
        card.innerHTML = `
            <div class="card-row">
                <span class="card-label">Date:</span>
                <span class="card-value">${escapeHtml(result.date)}</span>
            </div>
            <div class="card-row">
                <span class="card-label">Joueur:</span>
                <span class="card-value">${escapeHtml(result.prenom)} ${escapeHtml(result.nom)}</span>
            </div>
            <div class="card-row">
                <span class="card-label">Points Joueur:</span>
                <span class="card-value">${result.points_joueur}</span>
            </div>
            <div class="card-row">
                <span class="card-label">Points Adversaire:</span>
                <span class="card-value">${result.points_adv}</span>
            </div>
            <div class="card-row">
                <span class="card-label">Écart:</span>
                <span class="card-value"><span class="ecart-badge">+${result.ecart}</span></span>
            </div>
        `;
        mobileResults.appendChild(card);
    });
}

// Fonction pour copier tous les résultats
function copyAllResults() {
    if (currentResults.length === 0) return;
    
    const header = "Date\t\tPrénom\t\tNom\t\tPoints J.\tPoints Adv.\tÉcart";
    const separator = "-".repeat(80);
    const lines = [header, separator];
    
    currentResults.forEach(r => {
        const line = `${r.date}\t\t${r.prenom}\t\t${r.nom}\t\t${r.points_joueur}\t\t${r.points_adv}\t\t+${r.ecart}`;
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
        loadBtn.innerHTML = '<span class="btn-icon">🔄</span> Charger les Résultats';
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

// Charger automatiquement au démarrage (optionnel)
// window.addEventListener('load', loadResults);
