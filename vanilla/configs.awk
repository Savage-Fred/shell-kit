# Static source candidates only. Never evaluate shell code.
# ponytail: this is a word scanner, not a shell interpreter. Dynamic paths and
# complex heredocs stay unresolved; use a real shell parser if those must expand.
BEGIN {
    for (key in ENVIRON) vars[key] = ENVIRON[key]
    if ("CONFIGS_ZDOTDIR" in ENVIRON) vars["ZDOTDIR"]=ENVIRON["CONFIGS_ZDOTDIR"]
}
function expand(word,    out,i,c,q,end,name,value,pos,fallback) {
    out = ""; q = ""; valid = 1
    if (substr(word,1,1) == "~") {
        if (length(word)>1 && substr(word,2,1)!="/") { valid=0; return "" }
        out=ENVIRON["HOME"]; word=substr(word,2)
    }
    for (i=1; i<=length(word); i++) {
        c=substr(word,i,1)
        if (c=="\047" && q!="\"") { q=(q=="\047" ? "" : "\047"); continue }
        if (c=="\"" && q!="\047") { q=(q=="\"" ? "" : "\""); continue }
        if (c=="\\" && q!="\047") { out=out substr(word,++i,1); continue }
        if (q!="\047" && (c=="`" || (c=="$" && substr(word,i+1,1)=="("))) { valid=0; return "" }
        if (c=="$" && q!="\047") {
            name=""
            if (substr(word,i+1,1)=="{") {
                end=index(substr(word,i+2),"}")
                if (!end) { valid=0; return "" }
                name=substr(word,i+2,end-1); i+=end+1
            } else {
                while (substr(word,i+1,1) ~ /[A-Za-z0-9_]/ && i<length(word)) name=name substr(word,++i,1)
            }
            pos=index(name,":-")
            if (pos) {
                fallback=substr(name,pos+2); name=substr(name,1,pos-1)
                if (!(name in vars) || vars[name]=="") {
                    value=expand(fallback); if (!valid) return ""
                } else value=vars[name]
            } else {
                if (!(name in vars)) { valid=0; return "" }
                value=vars[name]
            }
            if (name !~ /^[A-Za-z_][A-Za-z0-9_]*$/) { valid=0; return "" }
            out=out value
        } else out=out c
    }
    if (q!="" || out ~ /[\t\r\n]/ || out ~ /[*?]/) valid=0
    return out
}
function continues(line,    i,c,q,word) {
    q=""; word=0
    for (i=1; i<=length(line); i++) {
        c=substr(line,i,1)
        if (c=="\\" && q!="\047") {
            if (i==length(line)) return 1
            i++; word=1; continue
        }
        if (c=="\047" && q!="\"") { q=(q=="\047" ? "" : "\047"); word=1; continue }
        if (c=="\"" && q!="\047") { q=(q=="\"" ? "" : "\""); word=1; continue }
        if (q!="") continue
        if (c=="#" && !word) return 0
        word=(c !~ /[ \t;|&(){}]/)
    }
    return 0
}
function consume(word,    value,name,pos) {
    if (want) {
        if (word=="--") return
        value=expand(word)
        if (valid && value!="") print NR "\t" value "\t" source_kind
        else print NR "\t?"
        want=0; command=0; return
    }
    if (command && (word=="source" || word==".")) { want=1; source_kind=word; return }
    if (command && word ~ /^[A-Za-z_][A-Za-z0-9_]*=/) {
        pos=index(word,"="); name=substr(word,1,pos-1); value=expand(substr(word,pos+1))
        if (valid) vars[name]=value; else delete vars[name]
        return
    }
    if (command && word ~ /^(then|do|else|elif|if|while|until|!|export|local|typeset|builtin|command)$/) command=1
    else command=0
}
{
    if (heredoc!="") {
        check=$0; if (strip_tabs) sub(/^\t+/,"",check)
        if (check==heredoc) heredoc=""
        next
    }
    line=pending $0; pending=""
    if (line ~ /\\$/ && continues(line)) { pending=substr(line,1,length(line)-1); next }
    command=1; want=0; word=""; quote=""; braces=0
    for (j=1; j<=length(line); j++) {
        ch=substr(line,j,1)
        if (ch=="\\" && quote!="\047") { word=word ch substr(line,++j,1); continue }
        if (ch=="\047" && quote!="\"") { quote=(quote=="\047" ? "" : "\047"); word=word ch; continue }
        if (ch=="\"" && quote!="\047") { quote=(quote=="\"" ? "" : "\""); word=word ch; continue }
        if (quote!="") { word=word ch; continue }
        if (ch=="#" && word=="") break
        if (!braces && substr(line,j,3)=="<<<") { j+=2; continue }
        if (!braces && ch=="<" && substr(line,j,2)=="<<" && substr(line,j,3)!="<<<") {
            rest=substr(line,j+2); strip_tabs=(substr(rest,1,1)=="-")
            if (strip_tabs) rest=substr(rest,2)
            sub(/^[ \t]+/,"",rest); split(rest,delim,/[ \t;|&]/)
            heredoc=delim[1]; gsub(/["\047]/,"",heredoc)
            # Multiple/expanded delimiters cannot be followed safely.
            if (heredoc !~ /^[A-Za-z0-9_]+$/ || rest ~ /<</) {
                print NR "\t!"; exit
            }
            break
        }
        # Keep an entire parameter expansion in its word, including nested
        # expansions and quoted braces. Its value may still be unresolved.
        if (ch=="{" && substr(word,length(word),1)=="$") braces++
        if (braces) {
            if (ch=="}") braces--
            word=word ch; continue
        }
        if (ch ~ /[ \t;|&(){}]/) {
            if (word!="") { consume(word); word="" }
            if (ch ~ /[;|&(){}]/) { if (want) { print NR "\t?"; want=0 }; command=1 }
        } else word=word ch
    }
    if (quote!="") { print NR "\t!"; exit }
    if (word!="") consume(word)
    if (want) print NR "\t?"
}
