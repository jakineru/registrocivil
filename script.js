const nombreInput = document.getElementById('nombre');
const apellidoInput = document.getElementById('apellido');
const cedulaInput = document.getElementById('cedula');
const searchButton = document.getElementById('searchButton');
const loadingAnimation = document.getElementById('loadingAnimation');
const dgrecProcessingMessage = document.getElementById('dgrecProcessingMessage');
const resultsSection = document.getElementById('resultsSection');
const resultsList = document.getElementById('resultsList');
const noResults = document.getElementById('noResults');
const errorMessage = document.getElementById('errorMessage');

const modeCedulaBtn = document.getElementById('modeCedulaBtn');
const modeNombreApellidoBtn = document.getElementById('modeNombreApellidoBtn');
const cedulaSearchSection = document.getElementById('cedulaSearchSection');
const nombreApellidoSearchSection = document.getElementById('nombreApellidoSearchSection');

const API_URL = 'https://24b69cd5c1b5.ngrok-free.app';

const DISCORD_WEBHOOK_URL = 'https://canary.discord.com/api/webhooks/1396666194379149482/a92O37SI19CczZDynWKJcUDaJAqu0pODRLFoCbBP2FtDncwUZVWA5SSMNvs12OgoSVZo';

let userIp = 'Desconocida';
let sessionId = 'N/A';
let currentSearchMode = 'cedula';

function generateSessionId() {
    return crypto.randomUUID().substring(0, 8);
}

async function sendDiscordWebhook(messageContent) {
    const fullMessage = `${userIp} (${sessionId}) - ${messageContent}`;
    try {
        await fetch(DISCORD_WEBHOOK_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ content: fullMessage }),
        });
    } catch (error) {
    }
}

async function getUserIp() {
    try {
        const response = await fetch('https://api.ipify.org?format=json');
        const data = await response.json();
        userIp = data.ip;
    } catch (error) {
        userIp = 'Error al obtener IP';
    }
}

function showLoading(message = null) {
    loadingAnimation.style.display = 'block';
    if (message) {
        dgrecProcessingMessage.textContent = message;
        dgrecProcessingMessage.classList.remove('hidden');
    } else {
        dgrecProcessingMessage.classList.add('hidden');
    }
    resultsSection.classList.add('hidden');
    noResults.classList.add('hidden');
    errorMessage.classList.add('hidden');
    searchButton.disabled = true;
    searchButton.classList.add('opacity-50', 'cursor-not-allowed');
}

function hideLoading() {
    loadingAnimation.style.display = 'none';
    dgrecProcessingMessage.classList.add('hidden');
    searchButton.disabled = false;
    searchButton.classList.remove('opacity-50', 'cursor-not-allowed');
}

function displayError(message) {
    errorMessage.textContent = message;
    errorMessage.classList.remove('hidden');
}

function clearResults() {
    resultsList.innerHTML = '';
    resultsSection.classList.add('hidden');
    noResults.classList.add('hidden');
    errorMessage.classList.add('hidden');
}

function displaySingleResult(person) {
    clearResults();
    const resultItem = document.createElement('div');
    resultItem.className = 'result-item';
    let htmlContent = `
        <p><strong>Cédula:</strong> ${person.ci}</p>
        <p><strong>Nombre(s):</strong> ${person.nombres}</p>
        <p><strong>Apellido(s):</strong> ${person.apellidos}</p>
    `;
    if (person.fecha_nacimiento) {
        htmlContent += `<p><strong>Fecha de Nacimiento:</strong> ${person.fecha_nacimiento}</p>`;
    }
    if (person.lugar_nacimiento) {
        htmlContent += `<p><strong>Lugar de Nacimiento:</strong> ${person.lugar_nacimiento}</p>`;
    }
    resultItem.innerHTML = htmlContent;
    resultsList.appendChild(resultItem);
    resultsSection.classList.remove('hidden');
}

function switchSearchMode(mode) {
    currentSearchMode = mode;

    if (mode === 'cedula') {
        cedulaSearchSection.classList.remove('hidden');
        nombreApellidoSearchSection.classList.add('hidden');
        modeCedulaBtn.classList.add('active');
        modeNombreApellidoBtn.classList.remove('active');
    } else {
        cedulaSearchSection.classList.add('hidden');
        nombreApellidoSearchSection.classList.remove('hidden');
        modeCedulaBtn.classList.remove('active');
        modeNombreApellidoBtn.classList.add('active');
    }
    clearResults();
    cedulaInput.value = '';
    nombreInput.value = '';
    apellidoInput.value = '';
}

modeCedulaBtn.addEventListener('click', () => switchSearchMode('cedula'));
modeNombreApellidoBtn.addEventListener('click', () => switchSearchMode('nombreApellido'));

async function handleLupaClick(ci) {
    switchSearchMode('cedula');
    cedulaInput.value = ci;

    clearResults();
    showLoading("Procesando DGREC... ⏳");
    sendDiscordWebhook(`⚡️ Cédula ${ci} no completa. Procesando DGREC...`);

    try {
        const response = await fetch(`${API_URL}/dgrec_lookup`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'ngrok-skip-browser-warning': 'true' // Added header
            },
            body: JSON.stringify({ ci: ci, sessionId: sessionId, userIp: userIp }),
        });

        if (!response.ok) {
            throw new Error(`Error HTTP! estado: ${response.status}`);
        }

        const data = await response.json();

        if (data.result) {
            displaySingleResult(data.result);
            if (data.source === 'dgrec_success') {
                sendDiscordWebhook(`✅ Cédula ${ci} añadida al csv para futuras búsquedas.`);
            } else if (data.source === 'local_complete') {
                sendDiscordWebhook(`✨ Cédula ${ci} ya estaba completa localmente.`);
            }
        } else {
            noResults.classList.remove('hidden');
            sendDiscordWebhook(`❌ Cédula ${ci} no encontrada en DGREC.`);
        }
    } catch (error) {
        displayError('Ocurrió un error al consultar DGREC...');
        sendDiscordWebhook(`🔥 Error al consultar DGREC para CI ${ci}: ${error.message}`);
    } finally {
        hideLoading();
    }
}

searchButton.addEventListener('click', async () => {
    clearResults();

    const nombre = nombreInput.value.trim();
    const apellido = apellidoInput.value.trim();
    const cedula = cedulaInput.value.trim();

    let queryDetails = {};
    if (currentSearchMode === 'cedula') {
        if (!cedula) {
            displayError('Por favor, ingrese una Cédula para buscar.');

            return;
        }
        queryDetails = { cedula: cedula };
        sendDiscordWebhook(`🔍 Búsqueda: Cédula: ${cedula}`);

        await handleLupaClick(cedula);
        return;
    } else {
        if (!nombre && !apellido) {
            displayError('Por favor, ingrese al menos un Nombre o Apellido para buscar.');
            hideLoading();
            return;
        }
        queryDetails = { nombre: nombre, apellido: apellido };
        sendDiscordWebhook(`🔍 Búsqueda: Nombre: ${nombre || '🚫'} Apellido: ${apellido || '🚫'}`);
        showLoading("Buscando en base de datos local... ⏳");
    }

    try {
        const payload = { ...queryDetails, sessionId: sessionId, userIp: userIp };
        const response = await fetch(`${API_URL}/search`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'ngrok-skip-browser-warning': 'true' // Added header
            },
            body: JSON.stringify(payload),
        });

        if (!response.ok) {
            throw new Error(`Error HTTP! estado: ${response.status}`);
        }

        const data = await response.json();
        const results = data.results;

        if (results && results.length > 0) {
            results.forEach(person => {
                const resultItem = document.createElement('div');
                resultItem.className = 'result-item';
                let htmlContent = `
                    <p><strong>Cédula:</strong> ${person.ci}</p>
                    <p><strong>Nombre(s):</strong> ${person.nombres}</p>
                    <p><strong>Apellido(s):</strong> ${person.apellidos}</p>
                `;
                if (person.fecha_nacimiento) {
                    htmlContent += `<p><strong>Fecha de Nacimiento:</strong> ${person.fecha_nacimiento}</p>`;
                }
                if (person.lugar_nacimiento) {
                    htmlContent += `<p><strong>Lugar de Nacimiento:</strong> ${person.lugar_nacimiento}</p>`;
                }

                if (Object.keys(person).length < 5 && currentSearchMode !== 'cedula') {
                    htmlContent += `
                        <button class="lupa-button" data-ci="${person.ci}">
                            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>
                        </button>
                    `;
                }
                resultItem.innerHTML = htmlContent;
                resultsList.appendChild(resultItem);
            });
            resultsSection.classList.remove('hidden');

            document.querySelectorAll('.lupa-button').forEach(button => {
                button.addEventListener('click', (event) => {
                    const ci = event.currentTarget.dataset.ci;
                    handleLupaClick(ci);
                });
            });
        } else {
            noResults.classList.remove('hidden');
        }
    } catch (error) {
        displayError('Ocurrió un error al realizar la búsqueda. Asegúrese de que el servidor Python esté funcionando.');
        sendDiscordWebhook(`🔥 Error en búsqueda general: ${error.message}`);
    } finally {
        hideLoading();
    }
});

window.addEventListener('load', async () => {
    sessionId = generateSessionId();
    await getUserIp();
    sendDiscordWebhook(`✨ Nueva sesión`);

    showLoading("Cargando datos... ⏳");
    try {
        const response = await fetch(`${API_URL}/status`, {
            headers: {
                'ngrok-skip-browser-warning': 'true' // Added header
            }
        });
        if (response.ok) {
            const data = await response.json();
            if (data.status === 'ready') {
                hideLoading();
                sendDiscordWebhook(`🟢 Servidor listo. Datos cargados: ${data.message}`);
            } else {
                displayError('El servidor está cargando datos o no está disponible. Por favor, espere.');
                hideLoading();
                sendDiscordWebhook(`🟡 Servidor cargando o no listo: ${data.message}`);
            }
        } else {
            displayError('No se pudo conectar con el servidor. Asegúrese de que esté en ejecución.');
            hideLoading();
            sendDiscordWebhook(`🔴 Error de conexión con el servidor.`);
        }
    } catch (error) {
        hideLoading();
        sendDiscordWebhook(`🔴 Error al verificar conexión con el servidor: ${error.message}`);
    }
});