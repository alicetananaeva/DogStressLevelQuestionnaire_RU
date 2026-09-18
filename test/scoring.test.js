import test from "node:test";
import assert from "node:assert/strict";
import { BEHAVIOR_ITEMS, calculateDslq, getHealthItems, validateDslq } from "../public/scoring.js";

function answers(main=2){return Object.fromEntries(BEHAVIOR_ITEMS.map((item)=>[item.key,item.type==="protective"?1:{main}]));}
function health(sex,value=-1){return Object.fromEntries(getHealthItems(sex).map((item)=>[item.code,value]));}

test("полный набор отрицательных симптомов валиден",()=>{const sex="Мужской";const a=answers();assert.equal(validateDslq(sex,a,health(sex)),true);assert.equal(calculateDslq(sex,a,health(sex)).total,0);});
test("защитный ответ Нет добавляет один балл",()=>{const sex="Женский";const a=answers();a.Dog_Play_FamHum=2;assert.equal(calculateDslq(sex,a,health(sex)).total,1);});
test("хронический симптом рассчитывается по частоте и дням",()=>{const sex="Мужской";const a=answers();a.Stereotypic={main:1,frequency:3,daysPerWeek:7,duration:2};assert.equal(calculateDslq(sex,a,health(sex)).total,1);});
test("медицинский признак больше месяца отмечается как chronic",()=>{const sex="Женский";const h=health(sex);h[1]=3;assert.equal(calculateDslq(sex,answers(),h).health,"chronic");});
test("неполные ответы не проходят проверку",()=>{const sex="Мужской";const a=answers();delete a.Anxiety;assert.equal(validateDslq(sex,a,health(sex)),false);});
