# L2-capital-velocity

**A discrete event simulation quantifying the capital efficiency of Bitcoin Layer 2 topologies.**

### 🎯 The Goal
To determine the economic crossover point between **Static Topologies** (Legacy Lightning Channels) and **Dynamic Topologies** (Ark Pools) for Liquidity Service Providers (LSPs).

This project simulates payment flows to measure **Capital Velocity** (Transaction Volume divided by Total Value Locked) required to maintain a <1% payment failure rate.

### 📊 The Models

We simulate two distinct operating models to test how liquidity fragmentation impacts the balance sheet:

1.  **The Static Model (Legacy Lightning)**
    *   **Topology:** Fragmented, bilateral liquidity (1-to-1 channels).
    *   **Constraint:** Capital locked in a channel cannot be used by other users.
    *   **Variables:** Rebalance Latency (Time to Splice/Swap) & Rebalance Cost.
    *   *Note:* By tweaking latency, this model simulates both standard Splicing (slow) and PeerSwap/Liquid (fast).

2.  **The Dynamic Model (Ark Protocol)**
    *   **Topology:** Pooled, shared liquidity (1-to-N factory).
    *   **Constraint:** Capital is re-allocated in discrete "Rounds" (e.g., every 10 minutes).
    *   **Variables:** Round Interval & Pool Size.

### 🧪 Methodology
This is a Monte Carlo simulation consisting of three phases:
1.  **Traffic Generation:** Generating synthetic datasets representing 1 month of payment flows (Pareto distributed, bursty, balanced vs. unbalanced).
2.  **Simulation Engine:** Processing events through both topology constraints.
3.  **Analysis:** Comparing the Total Locked Bitcoin required to service the same traffic volume in both models.

### 🚧 Status
*Research in progress.*

---

**Contributions & RFCs**
We are currently validating assumptions regarding LSP rebalancing behavior.