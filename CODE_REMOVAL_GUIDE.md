# 🗑️ Code Removal Guide - Transition to Prompt-Based System

This guide documents which files and directories can be safely removed when transitioning from the code-based trading simulator to the Claude prompt-based stock analysis system.

---

## ✅ Files to KEEP

These are essential for the prompt-based workflow:

```
📊 Essential Files:
├── HOLDINGS.md                    # Portfolio tracking (CRITICAL - update daily)
├── STOCK_ANALYSIS_GUIDE.md        # Usage instructions
├── README.md                      # Project overview
├── CODE_REMOVAL_GUIDE.md          # This file
├── .git/                          # Git repository (optional but recommended)
└── .gitignore                     # Git ignore rules (if using git)
```

---

## ❌ Files/Directories You CAN DELETE

### Backend Code (Python)
```
❌ Remove ALL Python backend code:

backend/                           # Entire backend directory
├── api/                          # API routes
├── models/                       # Database models
├── services/                     # Business logic
├── middleware/                   # Express middleware
├── utils/                        # Utility functions
└── server.js                     # Server entry point

Reason: No server needed for prompt-based analysis
```

### Frontend Code (React)
```
❌ Remove ALL frontend code:

frontend/                          # Entire frontend directory
├── src/                          # React source code
├── public/                       # Static assets
├── node_modules/                 # Dependencies (large!)
├── package.json                  # NPM dependencies
├── package-lock.json             # Lock file
└── build/                        # Built assets

Reason: No web dashboard needed for prompt-based workflow
```

### Python Trading System
```
❌ Remove Python trading simulator code:

analytics/                         # Analytics modules
config/                           # Configuration files
data/                             # Data collectors and processors
dashboard/                        # Dash dashboard
logs/                             # Log files
main/                             # Main orchestration
ml/                               # Machine learning modules
portfolio/                        # Portfolio management
signals/                          # Signal generation

main.py                           # Python entry point
requirements.txt                  # Python dependencies
test_system.py                    # System tests
```

### Database
```
❌ Remove database files:

database/                          # Database directory
├── trading.db                    # SQLite database
└── migrations/                   # Database migrations

Reason: Portfolio tracked in HOLDINGS.md instead
```

### Configuration & Setup
```
❌ Remove setup and config files:

.env                              # Environment variables
.env.example                      # Environment template
SETUP.md                          # Setup instructions
DEPLOYMENT_GUIDE.md               # Deployment guide
.venv/                            # Python virtual environment
.idea/                            # IDE settings

Reason: No installation or deployment needed
```

### Scripts
```
❌ Remove automation scripts:

.scripts/                          # Utility scripts
scripts/                          # Shell scripts

Reason: All operations done via Claude prompts
```

---

## 🔧 Files That Are Optional

### Git Repository
```
⚠️ Optional - Keep if you want version control:

.git/                             # Git repository
.gitignore                        # Git ignore rules

Decision: Keep if you want to track changes to HOLDINGS.md
```

### Documentation (Legacy)
```
⚠️ Optional - Can archive or delete:

SETUP.md                          # Old setup guide
DEPLOYMENT_GUIDE.md               # Old deployment guide

Decision: No longer relevant but may have useful info
```

---

## 📋 Removal Checklist

### Step 1: Backup Important Data
Before deleting anything:
```bash
# Backup your portfolio data if you had any
# Check if there's existing portfolio data in database/trading.db
# Or in any JSON/CSV files in data/ directories
```

### Step 2: Remove Backend & Frontend
```bash
# Remove backend
rm -rf backend/

# Remove frontend (including node_modules to save space)
rm -rf frontend/
```

### Step 3: Remove Python Trading System
```bash
# Remove Python modules
rm -rf analytics/ config/ data/ dashboard/ logs/ main/ ml/ portfolio/ signals/

# Remove Python entry points
rm main.py test_system.py requirements.txt

# Remove Python virtual environment
rm -rf .venv/
```

### Step 4: Remove Database
```bash
# Remove database directory
rm -rf database/
```

### Step 5: Remove Configuration
```bash
# Remove environment files
rm .env .env.example

# Remove old documentation
rm SETUP.md DEPLOYMENT_GUIDE.md

# Remove IDE settings (optional)
rm -rf .idea/

# Remove scripts
rm -rf .scripts/ scripts/
```

### Step 6: Clean Up Empty Directories
```bash
# Remove any remaining empty directories
find . -type d -empty -delete
```

---

## 📊 After Cleanup - Project Structure

Your project should look like this:
```
📊 Stock Analysis System/
├── .git/                          # Optional: Git repository
├── .gitignore                     # Optional: Git ignore
├── CODE_REMOVAL_GUIDE.md          # This file
├── HOLDINGS.md                    # Your portfolio tracker ⭐
├── README.md                      # Project overview
└── STOCK_ANALYSIS_GUIDE.md        # Usage instructions ⭐
```

**Total size**: < 1 MB (down from potentially 500+ MB with node_modules and .venv)

---

## 🎯 What You Get After Cleanup

### Before (Code-Based)
- 500+ MB of code and dependencies
- Python backend server
- React frontend dashboard
- Database setup required
- API keys needed
- Complex installation process
- Maintenance and updates required

### After (Prompt-Based)
- < 1 MB of markdown files
- No code execution needed
- No installation required
- No dependencies
- No API keys needed (Claude handles web search)
- Simple: just edit HOLDINGS.md and ask Claude

---

## ⚠️ Important Notes

### Data Migration
If you had existing portfolio data:
1. Check `database/trading.db` for historical trades
2. Export any important data before deleting
3. Transfer current positions to `HOLDINGS.md`
4. Record historical performance metrics if needed

### Git History
If you want to preserve git history:
```bash
# Keep .git/ directory
# Consider creating a new branch before cleanup
git checkout -b prompt-based-system
# Then perform cleanup
# Commit changes
git add -A
git commit -m "Transition to prompt-based stock analysis system"
```

### Reverting Back
If you want to restore code later:
```bash
# If you kept git history
git checkout main  # or your previous branch

# Or restore from backup if you made one
```

---

## 🚀 Post-Cleanup Steps

After removing unnecessary code:

1. **Update HOLDINGS.md**
   - Add your initial $200 capital
   - Add starting position (if any)
   - Set up watchlist

2. **Read STOCK_ANALYSIS_GUIDE.md**
   - Understand the prompt-based workflow
   - Learn example prompts
   - Review daily routine

3. **Start Using the System**
   ```
   Ask Claude: "Help me set up my initial portfolio in HOLDINGS.md.
   I want to start with $200 in cash."
   ```

4. **First Analysis**
   ```
   Ask Claude: "Analyze current market conditions.
   What stocks look promising for a $200 portfolio?"
   ```

---

## 🎓 Benefits of Simplified System

### Space Savings
- **Before**: 500+ MB
- **After**: < 1 MB
- **Savings**: 99.8% reduction in disk usage

### Complexity Reduction
- **Before**: Install Python, Node.js, dependencies, configure APIs
- **After**: Edit markdown files, ask Claude
- **Time Saved**: Hours of setup → Minutes to start

### Maintenance
- **Before**: Update dependencies, fix bugs, manage servers
- **After**: Update HOLDINGS.md
- **Effort**: Ongoing technical work → Simple file editing

### Accessibility
- **Before**: Need programming knowledge
- **After**: Just ask questions in natural language
- **Barrier**: High → None

---

## 📞 Need Help?

If you're unsure about deleting something:
```
Ask Claude: "Is it safe to delete [file/directory]?
I'm transitioning to the prompt-based system."
```

If you deleted something by mistake:
```
# If using git
git checkout [filename]

# Or ask Claude
"I accidentally deleted [file]. Do I need it for
the prompt-based system?"
```

---

## ✅ Final Cleanup Command

**CAUTION**: This removes everything except essential files.
**Make sure you have backups if needed!**

```bash
# One-command cleanup (use with caution!)
# This keeps only: .git, .gitignore, *.md files

find . -maxdepth 1 -type f ! -name "*.md" ! -name ".gitignore" -delete
find . -maxdepth 1 -type d ! -name "." ! -name ".." ! -name ".git" -exec rm -rf {} +
```

**Or safer, step-by-step approach** (recommended):
```bash
# Review what will be deleted
ls -la

# Delete directories one by one
rm -rf backend/
rm -rf frontend/
rm -rf analytics/
# ... etc (see checklist above)
```

---

**🎉 You're Done!**

Your simplified stock analysis system is ready. Just update HOLDINGS.md and start asking Claude for analysis!

**Next Step**: Ask Claude: "Help me analyze my first stock opportunity!"
