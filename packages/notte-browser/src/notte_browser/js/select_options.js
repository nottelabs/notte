select => {
    return Array.from(select.options).map(option => ({
        value: option.value,
        text: option.text
    }));
}
