_h3xrecon_completion() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    
    # Main commands
    opts="program config system queue list add del sendjob"
    
    # Subcommands based on previous word
    case "${prev}" in
        program)
            COMPREPLY=( $(compgen -W "list add del" -- ${cur}) )
            return 0
            ;;
        config)
            COMPREPLY=( $(compgen -W "add del list database" -- ${cur}) )
            return 0
            ;;
        system)
            COMPREPLY=( $(compgen -W "queue" -- ${cur}) )
            return 0
            ;;
        queue)
            COMPREPLY=( $(compgen -W "show messages flush worker job data" -- ${cur}) )
            return 0
            ;;
        list)
            COMPREPLY=( $(compgen -W "domains ips urls services" -- ${cur}) )
            return 0
            ;;
        add|del)
            COMPREPLY=( $(compgen -W "domain ip url" -- ${cur}) )
            return 0
            ;;
        *)
            ;;
    esac

    # Complete main commands if no specific subcommand completion
    COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
    return 0
}

complete -F _h3xrecon_completion h3xrecon