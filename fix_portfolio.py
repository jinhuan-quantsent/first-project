import sys

filepath = '/opt/fund-sentiment/v5-deploy/frontend/src/pages/PortfolioV5.tsx'
with open(filepath, 'r') as f:
    content = f.read()

# Fix 1: Add fetchPositionAdviceV5 to imports
old_import = "  decreasePosition,\n} from '../api/portfolioV5';"
new_import = "  decreasePosition,\n  fetchPositionAdviceV5,\n} from '../api/portfolioV5';"

if old_import in content:
    content = content.replace(old_import, new_import)
    print("Fix 1: Added fetchPositionAdviceV5 import")
else:
    print("Fix 1: SKIP - import pattern not found (may already be fixed)")
    if 'fetchPositionAdviceV5,' in content.split("} from '../api/portfolioV5'")[0]:
        print("  -> fetchPositionAdviceV5 already in imports")

# Fix 2: Replace detailResults with detailEntries
old_switch = """        detailResults.forEach((dr: any, idx: number) => {
          const code = safeItems[idx].fund_code;
          if (dr?.data?.signal_switched_today) {
            newSwitchMap[code] = true;
          }
        });"""

new_switch = """        detailEntries.forEach((entry) => {
          if (!entry) return;
          const [code, detail] = entry;
          if (detail?.signal_switched_today) {
            newSwitchMap[code] = true;
          }
        });"""

if old_switch in content:
    content = content.replace(old_switch, new_switch)
    print("Fix 2: Replaced detailResults with detailEntries")
else:
    print("Fix 2: SKIP - pattern not found")
    if 'detailResults' in content:
        print("  -> detailResults still present, need manual fix")

with open(filepath, 'w') as f:
    f.write(content)

# Final verify
with open(filepath, 'r') as f:
    verify = f.read()

print("\n=== Verification ===")
print("fetchPositionAdviceV5 imported:", 'fetchPositionAdviceV5,' in verify.split("} from '../api/portfolioV5'")[0] if "'../api/portfolioV5'" in verify else False)
print("detailResults gone:", 'detailResults' not in verify)
print("detailEntries.forEach present:", 'detailEntries.forEach' in verify)
