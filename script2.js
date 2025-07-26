document.addEventListener('DOMContentLoaded', function() {
            const API_URL = 'https://24b69cd5c1b5.ngrok-free.app';

            const ciInput = document.getElementById('cedula');
            const nombreInput = document.getElementById('nombre');
            const apellidoInput = document.getElementById('apellido');
            const searchButton = document.getElementById('searchButton');
            const clearButton = document.getElementById('clearButton');
            const resultsSection = document.getElementById('resultsSection');
            const resultsList = document.getElementById('resultsList');
            const noResults = document.getElementById('noResults');

            const modeCedulaBtn = document.getElementById('modeCedulaBtn');
            const modeNombreApellidoBtn = document.getElementById('modeNombreApellidoBtn');
            const cedulaSearchSection = document.getElementById('cedulaSearchSection');
            const nombreApellidoSearchSection = document.getElementById('nombreApellidoSearchSection');

            const loadingInitialData = document.getElementById('loadingInitialData');
            const loadingLocalSearch = document.getElementById('loadingLocalSearch');
            const loadingDGREC = document.getElementById('loadingDGREC');
            const errorMessage = document.getElementById('errorMessage');

            function showLoading(element) {
                hideAllMessages();
                resultsSection.classList.add('hidden');
                element.classList.remove('hidden');
            }

            function hideAllMessages() {
                loadingInitialData.classList.add('hidden');
                loadingLocalSearch.classList.add('hidden');
                loadingDGREC.classList.add('hidden');
                errorMessage.classList.add('hidden');
                noResults.classList.add('hidden');
            }

            function displayResults(data) {
                resultsList.innerHTML = '';
                hideAllMessages();
                resultsSection.classList.remove('hidden');

                if (data && data.length > 0) {
                    noResults.classList.add('hidden');
                    data.forEach(result => {
                        const card = document.createElement('div');
                        card.className = 'result-card mb-4';
                        card.innerHTML = `
                            <p><strong>CI:</strong> ${result.ci || 'N/A'}</p>
                            <p><strong>Nombres:</strong> ${result.nombres || 'N/A'}</p>
                            <p><strong>Apellidos:</strong> ${result.apellidos || 'N/A'}</p>
                            <p><strong>Fecha Nacimiento:</strong> ${result.fecha_nacimiento || 'N/A'}</p>
                            <p><strong>Lugar Nacimiento:</strong> ${result.lugar_nacimiento || 'N/A'}</p>
                        `;

                        if (result.ci) {
                            const lupaButton = document.createElement('button');
                            lupaButton.className = 'lupa-button-result';
                            lupaButton.innerHTML = `
                                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-search"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
                            `;
                            lupaButton.title = 'Buscar datos completos en DGREC';
                            lupaButton.onclick = () => {

                                modeCedulaBtn.click();

                                ciInput.value = result.ci;

                                searchButton.click();
                            };
                            card.appendChild(lupaButton);
                        }
                        resultsList.appendChild(card);
                    });
                } else {
                    noResults.classList.remove('hidden');
                }
            }

            async function lookupDGREC(ci) {
                showLoading(loadingDGREC);
                searchButton.disabled = true;
                try {
                    const sessionId = Math.random().toString(36).substring(2, 10);
                    const userIp = 'N/A';

                    const response = await fetch(`${API_URL}/dgrec_lookup`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'ngrok-skip-browser-warning': 'true', // Added header
                        },
                        body: JSON.stringify({ ci, sessionId, userIp }),
                    });

                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }

                    const data = await response.json();

                    if (data.result && Object.keys(data.result).length === 5) {

                        const currentResults = Array.from(resultsList.children).map(card => {
                            const ciText = card.querySelector('p strong:first-child').nextSibling.textContent.trim();
                            return {
                                ci: ciText,
                                nombres: card.querySelector('p:nth-child(2) strong').nextSibling.textContent.trim(),
                                apellidos: card.querySelector('p:nth-child(3) strong').nextSibling.textContent.trim(),
                                fecha_nacimiento: card.querySelector('p:nth-child(4) strong') ? card.querySelector('p:nth-child(4) strong').nextSibling.textContent.trim() : 'N/A',
                                lugar_nacimiento: card.querySelector('p:nth-child(5) strong') ? card.querySelector('p:nth-child(5) strong').nextSibling.textContent.trim() : 'N/A',
                            };
                        });

                        const updatedResults = currentResults.map(res => {
                            if (res.ci === data.result.ci) {
                                return data.result;
                            }
                            return res;
                        });
                        displayResults(updatedResults);
                    } else {

                        hideAllMessages();
                        noResults.classList.remove('hidden');
                    }

                } catch (error) {
                    console.error('Error al buscar en DGREC:', error);
                    hideAllMessages();
                    errorMessage.classList.remove('hidden');
                    resultsSection.classList.remove('hidden');
                    noResults.classList.remove('hidden');
                } finally {
                    hideAllMessages();
                    searchButton.disabled = false;
                }
            }

            async function searchData() {
                const ci = ciInput.value.trim();
                const nombre = nombreInput.value.trim();
                const apellido = apellidoInput.value.trim();

                const isCedulaMode = modeCedulaBtn.classList.contains('active');

                hideAllMessages();
                resultsList.innerHTML = '';
                resultsSection.classList.add('hidden');

                searchButton.disabled = true;

                let loadingMessageToShow = loadingLocalSearch;

                showLoading(loadingMessageToShow);

                try {
                    const sessionId = Math.random().toString(36).substring(2, 10);
                    const userIp = 'N/A';

                    const payload = {
                        ci: isCedulaMode ? ci : '',
                        nombre: !isCedulaMode ? nombre : '',
                        apellido: !isCedulaMode ? apellido : '',
                        sessionId,
                        userIp
                    };

                    const response = await fetch(`${API_URL}/search`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'ngrok-skip-browser-warning': 'true', // Added header
                        },
                        body: JSON.stringify(payload),
                    });

                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }

                    const data = await response.json();

                    if (data.search_type === "Cédula" && data.results && data.results.length > 0 && data.results[0].source === 'dgrec_success') {

                        showLoading(loadingDGREC);
                        await new Promise(resolve => setTimeout(resolve, 500));
                    }

                    displayResults(data.results);

                } catch (error) {
                    console.error('Error durante la búsqueda:', error);
                    hideAllMessages();
                    errorMessage.classList.remove('hidden');
                    resultsSection.classList.remove('hidden');
                    noResults.classList.remove('hidden');
                } finally {
                    hideAllMessages();
                    searchButton.disabled = false;
                }
            }

            async function loadInitialData() {
                showLoading(loadingInitialData);
                try {
                    const response = await fetch(`${API_URL}/status`, {
                        headers: {
                            'ngrok-skip-browser-warning': 'true', // Added header
                        }
                    });
                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }
                    const data = await response.json();
                    if (data.status === 'ready') {
                        hideAllMessages();

                        modeCedulaBtn.classList.add('active');
                        modeNombreApellidoBtn.classList.remove('active');
                        cedulaSearchSection.classList.remove('hidden');
                        nombreApellidoSearchSection.classList.add('hidden');
                    } else {

                        setTimeout(loadInitialData, 2000);
                    }
                } catch (error) {
                    console.error('Error al verificar el estado del servidor:', error);
                    hideAllMessages();
                    errorMessage.classList.remove('hidden');

                    setTimeout(loadInitialData, 5000);
                }
            }

            searchButton.addEventListener('click', searchData);

            if (clearButton) {
                clearButton.addEventListener('click', () => {
                    ciInput.value = '';
                    nombreInput.value = '';
                    apellidoInput.value = '';
                    resultsList.innerHTML = '';
                    hideAllMessages();
                    resultsSection.classList.add('hidden');
                });
            }

            if (modeCedulaBtn) {
                modeCedulaBtn.addEventListener('click', () => {
                    modeCedulaBtn.classList.add('active');
                    modeNombreApellidoBtn.classList.remove('active');
                    cedulaSearchSection.classList.remove('hidden');
                    nombreApellidoSearchSection.classList.add('hidden');

                    ciInput.value = '';
                    nombreInput.value = '';
                    apellidoInput.value = '';
                    resultsList.innerHTML = '';
                    hideAllMessages();
                    resultsSection.classList.add('hidden');
                });
            }

            if (modeNombreApellidoBtn) {
                modeNombreApellidoBtn.addEventListener('click', () => {
                    modeNombreApellidoBtn.classList.add('active');
                    modeCedulaBtn.classList.remove('active');
                    nombreApellidoSearchSection.classList.remove('hidden');
                    cedulaSearchSection.classList.add('hidden');

                    ciInput.value = '';
                    nombreInput.value = '';
                    apellidoInput.value = '';
                    resultsList.innerHTML = '';
                    hideAllMessages();
                    resultsSection.classList.add('hidden');
                });
            }

            window.addEventListener('load', loadInitialData);
        });