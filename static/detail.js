import {renderSaved} from './diagrams.js';
renderSaved(document.querySelector('#saved-diagrams'), JSON.parse(document.querySelector('#initial-diagrams').textContent));
