/**
 * 判断字符串是否包含可展开为多个结果的模式
 * @param {string} str - 要检查的字符串
 * @returns {boolean} - 如果字符串包含可展开的模式返回true，否则返回false
 */
function isRegexPattern(str) {
    // 空字符串直接返回false
    if (!str || typeof str !== 'string') {
        return false;
    }

    // 检查是否包含可展开的模式
    // 例如: [1-5], [a,b,c], {1,3}, (a|b)
    const expandablePatterns = /\[.+[-,].+\]|\{.+,.+\}|\(.+\|.+\)/;
    
    return expandablePatterns.test(str);
}

// 使用示例：
console.log(isRegexPattern('hello')); // false
console.log(isRegexPattern('[1-5]')); // true，数字范围
console.log(isRegexPattern('[a,b,c]')); // true，多个选项
console.log(isRegexPattern('test{1,3}')); // true，重复次数范围
console.log(isRegexPattern('(a|b)')); // true，多个选择
console.log(isRegexPattern('abc[123]')); // false，单个字符集
console.log(isRegexPattern('[1]')); // false，单个字符
console.log(isRegexPattern('a[x-z]b')); // true，字符范围