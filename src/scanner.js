#!/usr/bin/env node
/**
 * ╔═══════════════════════════════════════════════════════════════════╗
 * ║  POLYARB QUANTUM SCANNER v0.1                                     ║
 * ║  "Finding dollars on sale for 94 cents since 2026"               ║
 * ╚═══════════════════════════════════════════════════════════════════╝
 */

import { getMarkets, searchMarkets, findRelatedMarkets } from './polymarket.js';
import { generateQuantumReport, calculateQuantumPhaseShift, maxwellDemonScore } from './quantum.js';

const MIN_EDGE = 0.02; // 2% minimum edge to report
const MIN_VOLUME = 10000; // Minimum liquidity

console.log(`
╔═══════════════════════════════════════════════════════════════════╗
║  🔮 POLYARB QUANTUM ARBITRAGE SCANNER                             ║
║  ═══════════════════════════════════════════════════════════════  ║
║  Initializing Einstein-Heisenberg Phase Detection Matrix...       ║
║  Calibrating Maxwell's Demon...                                   ║
║  Loading Fibonacci-Mandelbrot Fractal Engine...                   ║
╚═══════════════════════════════════════════════════════════════════╝
`);

async function scan() {
  console.log('📡 Fetching markets from the Polymarket continuum...\n');
  
  let markets;
  try {
    markets = await getMarkets();
    console.log(`✓ Retrieved ${markets.length} active markets\n`);
  } catch (e) {
    console.error('❌ Failed to fetch markets:', e.message);
    console.log('\n🔄 Using mock data for demo...\n');
    markets = getMockMarkets();
  }
  
  // Find arbitrage opportunities
  const opportunities = [];
  
  // Type 1: Basic YES/NO arbitrage (same market)
  console.log('🔍 Scanning for Basic Arb (YES + NO < $1)...');
  for (const market of markets) {
    const arb = detectBasicArb(market);
    if (arb && arb.edge >= MIN_EDGE) {
      opportunities.push(arb);
    }
  }
  
  // Type 2: Related market arbitrage (correlated events)
  console.log('🔍 Scanning for Correlated Market Arb...');
  const groups = await findRelatedMarkets(markets);
  for (const group of groups) {
    const arb = detectCorrelatedArb(group);
    if (arb && arb.edge >= MIN_EDGE) {
      opportunities.push(arb);
    }
  }
  
  // Type 3: Mutually exclusive outcomes
  console.log('🔍 Scanning for Mutually Exclusive Arb...');
  const multiOutcome = markets.filter(m => (m.outcomes?.length || 0) > 2);
  for (const market of multiOutcome) {
    const arb = detectMutuallyExclusiveArb(market);
    if (arb && arb.edge >= MIN_EDGE) {
      opportunities.push(arb);
    }
  }
  
  // Sort by edge
  opportunities.sort((a, b) => b.edge - a.edge);
  
  // Report
  console.log(`\n${'═'.repeat(70)}`);
  console.log(`  SCAN COMPLETE: ${opportunities.length} opportunities detected`);
  console.log(`${'═'.repeat(70)}\n`);
  
  if (opportunities.length === 0) {
    console.log('😴 No arbitrage opportunities above threshold.');
    console.log('   The market is temporarily efficient. Check back later.\n');
    return;
  }
  
  for (const opp of opportunities.slice(0, 10)) {
    console.log(generateQuantumReport(opp));
    console.log(`  📊 Simple Summary:`);
    console.log(`     Type: ${opp.type}`);
    console.log(`     Edge: ${(opp.edge * 100).toFixed(2)}%`);
    console.log(`     Cost: $${opp.cost.toFixed(2)} → Payout: $${opp.payout.toFixed(2)}`);
    console.log(`     Markets: ${opp.marketCount}`);
    console.log(`     Volume: $${opp.totalVolume.toLocaleString()}`);
    console.log(`\n${'─'.repeat(70)}\n`);
  }
  
  return opportunities;
}

/**
 * Type 1: Basic YES + NO arbitrage
 * If YES + NO < $1, buy both, guaranteed profit
 */
function detectBasicArb(market) {
  const yesPrice = parseFloat(market.outcomePrices?.[0] || market.yes_price || 0.5);
  const noPrice = parseFloat(market.outcomePrices?.[1] || market.no_price || 0.5);
  
  const totalCost = yesPrice + noPrice;
  const edge = 1 - totalCost;
  
  if (edge <= 0) return null;
  
  return {
    type: 'BASIC_ARB',
    name: market.question || market.title || 'Unknown Market',
    edge,
    cost: totalCost,
    payout: 1.0,
    prices: [yesPrice, noPrice],
    marketCount: 1,
    totalVolume: parseFloat(market.volume || market.volumeNum || 0),
    markets: [market],
    strategy: `Buy YES @ $${yesPrice.toFixed(3)} + NO @ $${noPrice.toFixed(3)} = $${totalCost.toFixed(3)}`
  };
}

/**
 * Type 2: Correlated market arbitrage
 * Multiple markets about same event with different dates
 * If sum of all NO positions < $1, buy all NOs
 */
function detectCorrelatedArb(group) {
  const { event, markets } = group;
  
  if (markets.length < 2) return null;
  
  // Get NO prices for all markets
  const noPrices = markets.map(m => {
    return parseFloat(m.outcomePrices?.[1] || m.no_price || 0.5);
  });
  
  const totalNoCost = noPrices.reduce((a, b) => a + b, 0);
  
  // If event happens in ANY timeframe, all NO positions after it lose
  // But if event NEVER happens, all NO positions pay $1 each
  // Edge: if totalNoCost < markets.length (i.e., avg NO price < $1)
  
  // More conservative: check if buying NO on ALL markets costs less than
  // the minimum guaranteed payout
  const minPayout = markets.length - 1; // Worst case: event happens on first date
  const edge = (minPayout - totalNoCost) / markets.length;
  
  if (edge <= 0) return null;
  
  return {
    type: 'CORRELATED_DATE_ARB',
    name: `${event} (${markets.length} date markets)`,
    edge,
    cost: totalNoCost,
    payout: minPayout,
    prices: noPrices,
    marketCount: markets.length,
    totalVolume: markets.reduce((sum, m) => sum + parseFloat(m.volume || m.volumeNum || 0), 0),
    markets,
    strategy: `Buy NO on all ${markets.length} dates. Cost: $${totalNoCost.toFixed(2)}, Min payout: $${minPayout}`
  };
}

/**
 * Type 3: Mutually exclusive outcomes
 * If market has multiple outcomes where exactly one must win,
 * sum of all YES prices should = $1
 */
function detectMutuallyExclusiveArb(market) {
  const outcomes = market.outcomes || [];
  if (outcomes.length < 3) return null;
  
  // Handle both array and string formats
  let prices = [];
  if (Array.isArray(market.outcomePrices)) {
    prices = market.outcomePrices.map(p => parseFloat(p));
  } else if (typeof market.outcomePrices === 'string') {
    try {
      prices = JSON.parse(market.outcomePrices).map(p => parseFloat(p));
    } catch { return null; }
  } else {
    return null;
  }
  
  if (prices.length !== outcomes.length) return null;
  
  const totalCost = prices.reduce((a, b) => a + b, 0);
  const edge = 1 - totalCost;
  
  if (edge <= 0) return null;
  
  return {
    type: 'MUTUALLY_EXCLUSIVE_ARB',
    name: market.question || market.title || 'Unknown Market',
    edge,
    cost: totalCost,
    payout: 1.0,
    prices,
    marketCount: 1,
    totalVolume: parseFloat(market.volume || market.volumeNum || 0),
    markets: [market],
    strategy: `Buy YES on all ${outcomes.length} outcomes. One must win. Cost: $${totalCost.toFixed(3)}`
  };
}

/**
 * Mock markets for demo when API fails
 */
function getMockMarkets() {
  return [
    {
      question: 'US strikes Iran by March 2026?',
      outcomePrices: ['0.15', '0.82'],
      volume: '1500000',
      outcomes: ['Yes', 'No']
    },
    {
      question: 'US strikes Iran by April 2026?',
      outcomePrices: ['0.22', '0.75'],
      volume: '800000',
      outcomes: ['Yes', 'No']
    },
    {
      question: 'US strikes Iran by June 2026?',
      outcomePrices: ['0.35', '0.62'],
      volume: '500000',
      outcomes: ['Yes', 'No']
    },
    {
      question: 'Bitcoin above $100k end of 2026?',
      outcomePrices: ['0.45', '0.52'],
      volume: '5000000',
      outcomes: ['Yes', 'No']
    },
    {
      question: 'Who wins 2028 Presidential Election?',
      outcomePrices: ['0.35', '0.30', '0.15', '0.10', '0.05'],
      volume: '10000000',
      outcomes: ['DeSantis', 'Newsom', 'Trump', 'Harris', 'Other']
    }
  ];
}

// Run scanner
scan().then(results => {
  if (results?.length > 0) {
    console.log('\n💡 Paper Trading Simulation:');
    console.log('   If you bought $1000 worth of the top opportunity:');
    const top = results[0];
    const shares = 1000 / top.cost;
    const profit = (shares * top.payout) - 1000;
    console.log(`   Investment: $1,000`);
    console.log(`   Expected Return: $${(1000 + profit).toFixed(2)}`);
    console.log(`   Profit: $${profit.toFixed(2)} (${(top.edge * 100).toFixed(2)}%)`);
    console.log(`\n   ⚠️  This is PAPER TRADING. No real money involved.`);
  }
}).catch(console.error);
