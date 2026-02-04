#!/usr/bin/env node
/**
 * ╔═══════════════════════════════════════════════════════════════════╗
 * ║  POLYARB QUANTUM WATCHER                                          ║
 * ║  Continuous monitoring with Telegram alerts                       ║
 * ╚═══════════════════════════════════════════════════════════════════╝
 */

import { getMarkets, findRelatedMarkets } from './polymarket.js';
import { generateQuantumReport, calculateQuantumPhaseShift } from './quantum.js';

const SCAN_INTERVAL = 60000; // 1 minute
const MIN_EDGE = 0.03; // 3% minimum for alerts
const TELEGRAM_BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN;
const TELEGRAM_CHAT_ID = process.env.TELEGRAM_CHAT_ID;

const seenOpportunities = new Set();

console.log(`
╔═══════════════════════════════════════════════════════════════════╗
║  🔮 POLYARB QUANTUM WATCHER ACTIVATED                             ║
║  ═══════════════════════════════════════════════════════════════  ║
║  Scan Interval: ${(SCAN_INTERVAL / 1000)}s                                              ║
║  Min Edge: ${(MIN_EDGE * 100)}%                                                    ║
║  Telegram: ${TELEGRAM_BOT_TOKEN ? '✓ Enabled' : '✗ Disabled (set TELEGRAM_BOT_TOKEN)'}                              ║
╚═══════════════════════════════════════════════════════════════════╝
`);

async function sendTelegramAlert(message) {
  if (!TELEGRAM_BOT_TOKEN || !TELEGRAM_CHAT_ID) {
    console.log('[Telegram disabled] Would send:', message.substring(0, 100) + '...');
    return;
  }
  
  try {
    await fetch(`https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        chat_id: TELEGRAM_CHAT_ID,
        text: message,
        parse_mode: 'HTML'
      })
    });
  } catch (e) {
    console.error('Telegram error:', e.message);
  }
}

async function watchCycle() {
  const timestamp = new Date().toISOString().substring(11, 19);
  console.log(`\n[${timestamp}] 🔍 Scanning quantum field...`);
  
  let markets;
  try {
    markets = await getMarkets();
  } catch (e) {
    console.log(`[${timestamp}] ⚠️  API error, will retry: ${e.message}`);
    return;
  }
  
  const opportunities = [];
  
  // Scan for basic arb
  for (const market of markets) {
    const yesPrice = parseFloat(market.outcomePrices?.[0] || 0.5);
    const noPrice = parseFloat(market.outcomePrices?.[1] || 0.5);
    const edge = 1 - (yesPrice + noPrice);
    
    if (edge >= MIN_EDGE) {
      const id = `basic:${market.id || market.question}`;
      opportunities.push({
        id,
        type: 'BASIC',
        name: market.question || 'Unknown',
        edge,
        yesPrice,
        noPrice
      });
    }
  }
  
  // Scan correlated markets
  const groups = await findRelatedMarkets(markets);
  for (const group of groups) {
    if (group.markets.length < 2) continue;
    
    const noPrices = group.markets.map(m => parseFloat(m.outcomePrices?.[1] || 0.5));
    const totalCost = noPrices.reduce((a, b) => a + b, 0);
    const minPayout = group.markets.length - 1;
    const edge = (minPayout - totalCost) / group.markets.length;
    
    if (edge >= MIN_EDGE) {
      const id = `correlated:${group.event}`;
      opportunities.push({
        id,
        type: 'CORRELATED',
        name: group.event,
        edge,
        marketCount: group.markets.length,
        totalCost,
        minPayout
      });
    }
  }
  
  // Report new opportunities
  for (const opp of opportunities) {
    if (!seenOpportunities.has(opp.id)) {
      seenOpportunities.add(opp.id);
      
      console.log(`\n🚨 NEW OPPORTUNITY DETECTED!`);
      console.log(`   Type: ${opp.type}`);
      console.log(`   Market: ${opp.name}`);
      console.log(`   Edge: ${(opp.edge * 100).toFixed(2)}%`);
      
      // Calculate quantum metrics for fun
      const phase = calculateQuantumPhaseShift([opp.yesPrice || 0.5, opp.noPrice || 0.5]);
      console.log(`   Phase Shift: ${phase.phaseAngle.toFixed(2)}°`);
      console.log(`   Wave Function: ${phase.waveFunction}`);
      
      // Send Telegram alert
      const alert = `
🔮 <b>POLYARB ALERT</b>

<b>Type:</b> ${opp.type}
<b>Market:</b> ${opp.name.substring(0, 50)}
<b>Edge:</b> ${(opp.edge * 100).toFixed(2)}%
${opp.type === 'BASIC' ? 
  `<b>YES:</b> $${opp.yesPrice.toFixed(3)}
<b>NO:</b> $${opp.noPrice.toFixed(3)}` :
  `<b>Markets:</b> ${opp.marketCount}
<b>Total Cost:</b> $${opp.totalCost.toFixed(2)}`}

<i>Phase Angle: ${phase.phaseAngle.toFixed(2)}°</i>
<i>Wave: ${phase.waveFunction}</i>

⚠️ Paper trade only. DYOR.
      `.trim();
      
      await sendTelegramAlert(alert);
    }
  }
  
  // Clean old opportunities (reset every hour)
  if (seenOpportunities.size > 1000) {
    seenOpportunities.clear();
    console.log('[Housekeeping] Cleared opportunity cache');
  }
  
  console.log(`[${timestamp}] ✓ Scan complete. ${opportunities.length} opportunities above ${MIN_EDGE * 100}% threshold.`);
}

// Main loop
async function main() {
  while (true) {
    try {
      await watchCycle();
    } catch (e) {
      console.error('Watch cycle error:', e);
    }
    await new Promise(r => setTimeout(r, SCAN_INTERVAL));
  }
}

main();
