#!/usr/bin/env node
/**
 * PolyArb - Polymarket Arbitrage Scanner
 * Main entry point
 */

import { spawn } from 'child_process';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __dirname = dirname(fileURLToPath(import.meta.url));

const command = process.argv[2] || 'scan';

console.log(`
    ____        __      ___         __  
   / __ \\____  / /_  __/   |  _____/ /_ 
  / /_/ / __ \\/ / / / / /| | / ___/ __ \\
 / ____/ /_/ / / /_/ / ___ |/ /  / /_/ /
/_/    \\____/_/\\__, /_/  |_/_/  /_.___/ 
              /____/                     
                                         
  Quantum Arbitrage Scanner v0.1
  "The market can stay irrational longer than you can stay solvent"
  
`);

if (command === 'scan') {
  import('./scanner.js');
} else if (command === 'watch') {
  import('./watcher.js');
} else {
  console.log('Usage: polyarb [scan|watch]');
  console.log('  scan  - One-time arbitrage scan');
  console.log('  watch - Continuous monitoring with alerts');
}
